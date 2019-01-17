import functools
import tensorflow as tf

from lmnet.networks.classification.base import Base


class LmResnet(Base):
    """Residual network (ResNet) of 18-layers for classification

    This ResNet-18 is modified from the ImageNet version of ResNet-18 of the original paper
            Deep Residual Learning for Image Recognition (https://arxiv.org/abs/1512.03385)

    - first layer is 3x3 convolution layer with stride 1 instead of 7x7 conv with stride 2,
      like the CIFAR-10 version of ResNet-18 in the paper.
    - The 3x3 max pooling with stride 2 is not used in this architecture.
    - In each residual block, batch normalization (BN) is after the add, to be specific, a
      pre-activation variant of residual block is used.
    - Utilizing Space-to-Depth operator for each the transition layer, convolution op with
      strides of 2 is replaced with space-to-depth.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.custom_getter = None
        self.activation = tf.nn.relu
        self.weight_decay_rate = 0.0001
        self.init_ch = 64
        self.num_blocks = {
            18: [2, 2, 2, 2],
            34: [3, 4, 6, 3],
            50: [3, 4, 6, 3],
        }[18]

    @staticmethod
    def _batch_norm(inputs, training):
        return tf.contrib.layers.batch_norm(
            inputs,
            decay=0.997,
            updates_collections=None,
            is_training=training,
            activation_fn=None,
            center=True,
            scale=True)

    def _conv2d_fix_padding(self, inputs, filters, kernel_size, strides):
        if strides == 2:
            inputs = self._space_to_depth(inputs, name="pool")

        return tf.layers.conv2d(
            inputs, filters, kernel_size,
            padding="SAME",
            kernel_initializer=tf.contrib.layers.xavier_initializer(),
            use_bias=False)

    def _space_to_depth(self, inputs=None, block_size=2, name=''):
        if self.data_format != 'NHWC':
            inputs = tf.transpose(inputs, perm=[self.data_format.find(d) for d in 'NHWC'])

        output = tf.space_to_depth(inputs, block_size=block_size, name=name)

        if self.data_format != 'NHWC':
            output = tf.transpose(output, perm=['NHWC'.find(d) for d in self.data_format])
        return output

    def basicblock(self, x, out_ch, strides, training):
        in_ch = x.get_shape().as_list()[1 if self.data_format in ['NCHW', 'channels_first'] else 3]
        shortcut = x

        x = self._batch_norm(x, training)
        x = self.activation(x)

        x = self._conv2d_fix_padding(x, out_ch, 3, strides)
        x = self._batch_norm(x, training)
        x = self.activation(x)

        x = self._conv2d_fix_padding(x, out_ch, 3, 1)

        if in_ch != out_ch:
            shortcut = tf.nn.avg_pool(shortcut, ksize=[1, strides, strides, 1],
                                      strides=[1, strides, strides, 1], padding='VALID')
            shortcut = tf.pad(shortcut, [[0, 0], [0, 0], [0, 0],
                              [(out_ch - in_ch) // 2, (out_ch - in_ch) // 2]])
        return shortcut + x

    def resnet_group(self, x, out_ch, count, strides, training, name):
        with tf.variable_scope(name, custom_getter=self.custom_getter):
            for i in range(0, count):
                with tf.variable_scope('block{}'.format(i)):
                    x = self.basicblock(x, out_ch,
                                        strides if i == 0 else 1,
                                        training)
        return x

    def base(self, images, is_training):
        """Base network.

        Args:
            images: Input images.
            is_training: A flag for if it is training or not.
        Returns:
            tf.Tensor: Inference result.
        """
        self.images = images

        x = self._conv2d_fix_padding(images, self.init_ch, 3, 1)
        x = self.resnet_group(x, self.init_ch * 1, self.num_blocks[0], 1, is_training, 'group0')
        x = self.resnet_group(x, self.init_ch * 2, self.num_blocks[1], 2, is_training, 'group1')
        x = self.resnet_group(x, self.init_ch * 4, self.num_blocks[2], 2, is_training, 'group2')
        x = self.resnet_group(x, self.init_ch * 8, self.num_blocks[3], 2, is_training, 'group3')
        x = self._batch_norm(x, is_training)
        x = tf.nn.relu(x)

        # global average pooling
        h = x.get_shape()[1].value
        w = x.get_shape()[2].value
        x = tf.layers.average_pooling2d(name="gap", inputs=x, pool_size=[h, w], padding="VALID", strides=1)

        if tf.rank(x) != 2:
            shape = x.get_shape().as_list()
            flattened_shape = functools.reduce(lambda x, y: x * y, shape[1:])
            x = tf.reshape(x, [-1, flattened_shape], name='reshape')
        output = tf.contrib.layers.fully_connected(x, self.num_classes, activation_fn=None, scope='linear')

        return output


class LmResnetQuantize(LmResnet):
    version = 1.0

    def __init__(
            self,
            activation_quantizer=None,
            activation_quantizer_kwargs=None,
            weight_quantizer=None,
            weight_quantizer_kwargs=None,
            *args,
            **kwargs
    ):
        super().__init__(
            *args,
            **kwargs
        )

        assert weight_quantizer
        assert activation_quantizer

        activation_quantizer_kwargs = activation_quantizer_kwargs if activation_quantizer_kwargs is not None else {}
        weight_quantizer_kwargs = weight_quantizer_kwargs if weight_quantizer_kwargs is not None else {}

        self.activation = activation_quantizer(**activation_quantizer_kwargs)
        weight_quantization = weight_quantizer(**weight_quantizer_kwargs)
        self.custom_getter = functools.partial(self._quantized_variable_getter,
                                               weight_quantization=weight_quantization)

    @staticmethod
    def _quantized_variable_getter(getter, name, weight_quantization=None, *args, **kwargs):
        """Get the quantized variables.
        Use if to choose or skip the target should be quantized.
        Args:
            getter: Default from tensorflow.
            name: Default from tensorflow.
            weight_quantization: Callable object which quantize variable.
            args: Args.
            kwargs: Kwargs.
        """
        assert callable(weight_quantization)
        var = getter(name, *args, **kwargs)
        with tf.variable_scope(name):
            # Apply weight quantize to variable whose last word of name is "kernel".
            if "kernel" == var.op.name.split("/")[-1]:
                return weight_quantization(var)
        return var
