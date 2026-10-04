# 第三方组件与许可边界

根目录 `LICENSE` 只覆盖本项目自有代码与文档，不改变任何第三方组件的许可。源码仓库不包含运行时、引擎二进制或模型。这里保留的上游完整许可文本用于说明依赖来源，也供打包时一并保留。

## AI 引擎和模型

- **waifu2x-ncnn-vulkan，20250915**：nihui，MIT。见 `licenses/waifu2x-ncnn-MIT.txt` 和[对应版本源码](https://github.com/nihui/waifu2x-ncnn-vulkan/tree/20250915)
- **waifu2x CUnet / upconv 模型**：nagadomi，MIT。见 `licenses/waifu2x-models-MIT.txt`；模型作者在[官方问题中的回复](https://github.com/nagadomi/waifu2x/issues/478#issuecomment-5003816684)明确确认权重使用 MIT
- **ncnn**：BSD-3-Clause 及其内附第三方许可，见 `licenses/ncnn-BSD.txt`
- **glslang、libjpeg-turbo、libpng、libwebp、zlib-ng、dirent**：各自适用 `licenses/` 中对应的完整许可与声明；不能由本项目的 MIT 许可替代

上游演示图片不属于本项目发布内容，其中可能包含非商业限制的图片。不要因为模型是 MIT 就把演示图片一并打包。

## Python 与 Pillow

- **Python 3.14.8 官方 Windows x64 embedded distribution**：PSF 许可及其附带第三方条款，完整文本为 `licenses/Python-3.14.8-LICENSE.txt`；运行时内的 `runtime/LICENSE.txt` 也须保留。[官方发布页](https://www.python.org/downloads/release/python-3148/)
- **Pillow 12.3.0**：HPND 许可及其内附依赖条款，完整文本为 `licenses/Pillow-12.3.0-LICENSE.txt`；分发 wheel 的内容时必须保留其 `.dist-info/licenses/`。[PyPI 发布页](https://pypi.org/project/pillow/12.3.0/)

这些文件是从用于本版本的官方 Python 分发包及 Pillow wheel 中保留的完整文本，并非本项目重新授予的许可。

## Microsoft 运行库

官方 Windows 引擎包含 `vcomp140.dll`，官方 Python 嵌入包包含 `vcruntime140.dll` 与 `vcruntime140_1.dll`。它们属于 Microsoft Distributable Code，不是 MIT 许可的本项目代码。

Python 完整许可中的 “Microsoft Distributable Code” 一节说明再分发要求。引擎运行库还应按适用的 Microsoft 条款核对分发权及最终用户条款。参见 [Microsoft 官方再分发说明](https://learn.microsoft.com/en-us/cpp/windows/redistributing-visual-cpp-files?view=msvc-170)。保留第三方文件原有版权与声明；本项目 MIT 许可不提供 Microsoft 组件的额外授权。

公开二进制前，应根据实际包含的文件复核所有条款。只发布本源码仓库不会再分发这些 DLL。
