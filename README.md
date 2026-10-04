# 素材清晰工坊 · v0.1.1 测试版

一个中文、本地运行的图片批量降噪与放大工具，使用 [waifu2x-ncnn-vulkan](https://github.com/nihui/waifu2x-ncnn-vulkan)。适合先试一张，再处理一整个素材文件夹。

**兼容性提醒：** 便携版面向 Windows 10/11 x64，需要支持 Vulkan 的显卡与驱动。Windows 原生启动、文件夹选择器及不同显卡尚未完成实机验收。CPU 是实验选项，已知测试环境中运行失败，不保证可用，也不会自动作为 GPU 的后备。

## 可以做什么

- 批量处理 PNG、JPEG、WebP、BMP、TIFF 静态 8 位图片，可包含子目录
- 默认把长边统一到 2048，保留比例；1536×1024 会得到 2048×1365
- CUnet / upconv 模型、降噪强度、目标长边和分块大小可调
- 独立处理透明通道，尽量减少透明素材边缘黑边
- 原图只读，新建输出目录，保留子目录和原文件名，避免覆盖
- 每张成功图片仅保存一个正式 `原文件名_AI.png`，不生成对比图
- 处理报告单独写入工具的 `logs/`，可以取消并保留已完成结果

**长边是统一尺寸，不是只放大：原图更大时也会缩小。** 强降噪可能抹去细节；AI 不能保证恢复原图中不存在或已经丢失的真实内容。

## 下载与使用

本仓库保存源码、文档和测试，不包含用户图片、Python 运行时、AI 引擎或模型权重。GitHub 的 “Source code” 下载不是可直接双击运行的便携版。

如果此项目的 Releases 提供 Windows 便携包，首次使用需将主程序、AI 引擎、模型三个 ZIP 解压到同一位置，合并成一个 `ArtUpscaler` 文件夹，再双击 `启动素材清晰工坊.cmd`。没有提供附件时，请按下面的源码运行步骤操作。

详细说明见 [中文使用说明](docs/使用说明.md)。建议用“长边 2048、温和降噪、CUnet、GPU、分块 128”先试一张，检查透明边缘与细节后再批量处理。

## 从源码运行

开发验证使用 Python 3.12.14 与 Pillow 12.3.0；Windows 便携包采用 Python 3.14.8 x64。源码需要 Python 3.12 或更新版本，但没有测试所有组合。

```sh
python -m venv .venv
# Windows：.venv\Scripts\activate
# Linux：source .venv/bin/activate
python -m pip install -r requirements.txt
```

从 [waifu2x 官方 20250915 发布页](https://github.com/nihui/waifu2x-ncnn-vulkan/releases/tag/20250915) 获取与你的系统匹配的引擎，将可执行文件、运行依赖、`models-cunet` 和 `models-upconv_7_anime_style_art_rgb` 放入 `engine/`。保留其许可证。不要复制上游演示图片。

```sh
python app.py
# 也可指定引擎目录：python app.py --engine /path/to/engine
```

程序仅监听 `127.0.0.1`，自动打开带有本次随机访问令牌的本地网页。不需要账号，不上传图片，不发送遥测；关闭程序后令牌失效。不要公开分享启动窗口中的完整网址。

Windows 的文件夹按钮调用系统选择器；其他系统请输入绝对路径，手动打开结果目录。Linux 引擎测试通过不代表提供了完整 Linux 桌面体验。下载依赖需要联网，处理图片本身不需要联网。

## 测试与构建

```sh
python -m unittest discover -s tests -p "test_*.py" -v
node tests/test_ui.js
python scripts/build_source.py
```

Python 测试生成合成图片；其中替身引擎只验证文件与流程规则，不代表真实 AI 效果。JavaScript 测试检查脚本与 DOM 逻辑，不代表 Windows GUI 实机验收。

- [构建和打包说明](docs/构建说明.md)
- [v0.1.1 发布说明](docs/RELEASE-v0.1.1.md)
- [验证范围](docs/验证范围.md)

## 隐私与许可

输入和输出路径、文件名及错误可能保存在本地 `logs/` 报告中。提交问题时请先移除个人路径、令牌及未授权素材；不要直接上传整个工具目录。

本项目自有应用代码按 [MIT](LICENSE) 许可发布。依赖和便携包里的各组件保留自己的许可证，**整个依赖包不统一称为 MIT**。waifu2x 模型作者已[明确确认模型权重采用 MIT](https://github.com/nagadomi/waifu2x/issues/478#issuecomment-5003816684)。Python、Pillow、Microsoft 运行库及引擎的其他依赖分别适用其条款，详见 [第三方说明](THIRD_PARTY_NOTICES.md)。工具许可不授予任何输入素材的版权，请仅处理你有权使用的图片。
