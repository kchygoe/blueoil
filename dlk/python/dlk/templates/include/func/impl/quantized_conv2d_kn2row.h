/* Copyright 2018 The Blueoil Authors. All Rights Reserved.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
==============================================================================*/

#ifndef DLK_FUNC_IMPL_QUANTIZED_CONV2D_KN2ROW_H_INCLUDED
#define DLK_FUNC_IMPL_QUANTIZED_CONV2D_KN2ROW_H_INCLUDED

#include "global.h"
#include "operators.h" // FIXME(nikolay): for convolution_parameters definition, rid of it later
#include "tensor_view.h"

namespace dlk {

namespace impl {

using kn2row_input_elem_t = QUANTIZED_PACKED;
using kn2row_input_t = TensorView<kn2row_input_elem_t, MemoryLayout::ChHWBCl>;
using kn2row_kernel_t = TensorView<QUANTIZED_PACKED_KERNEL, MemoryLayout::HWNC>;
using kn2row_fpga_kernel_t = TensorView<QUANTIZED_PACKED_KERNEL, MemoryLayout::OhIhHWOlIl>;

void quantized_ohwi_to_hwoi(const kernel_t& ohwi, const kn2row_kernel_t& hwoi, const binary_convolution_parameters& p);

#ifndef RUN_ON_FPGA
void QuantizedConv2DKn2Row(const kn2row_input_t& input,
                                  const kn2row_kernel_t& kernel,
                                  const binary_convolution_parameters &p);
#else
void TCAConv2d(const kn2row_input_t& input,
    const kn2row_fpga_kernel_t& kernel,
    const binary_convolution_parameters &p);
#endif


} // namespace impl

} // namespace dlk

#endif // DLK_FUNC_IMPL_QUANTIZED_CONV2D_KN2ROW_H_INCLUDED
