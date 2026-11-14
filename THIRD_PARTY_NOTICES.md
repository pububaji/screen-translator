# 第三方组件声明

本项目在运行与打包发行时使用了以下开源组件。各组件的版权归其作者所有，
完整许可证文本可在对应项目的仓库或安装包中找到。

| 组件 | 许可证 | 项目地址 |
|---|---|---|
| Python | PSF License | https://www.python.org/ |
| Tcl/Tk | BSD-style | https://www.tcl.tk/ |
| RapidOCR (rapidocr-onnxruntime) | Apache-2.0 | https://github.com/RapidAI/RapidOCR |
| ONNX Runtime | MIT | https://github.com/microsoft/onnxruntime |
| OpenCV | Apache-2.0 | https://github.com/opencv/opencv |
| NumPy | BSD-3-Clause | https://github.com/numpy/numpy |
| Pillow | HPND / MIT-CMU | https://github.com/python-pillow/Pillow |
| pystray | LGPL-3.0 | https://github.com/str4d/pystray |
| sv-ttk | MIT | https://github.com/rdbende/Sun-Valley-ttk-theme |
| keyboard | MIT | https://github.com/boppreh/keyboard |
| mss | MIT | https://github.com/BoboTiG/python-mss |
| curl_cffi | MIT | https://github.com/lexiforest/curl_cffi |
| requests | Apache-2.0 | https://github.com/psf/requests |
| urllib3 | MIT | https://github.com/urllib3/urllib3 |
| certifi | MPL-2.0 | https://github.com/certifi/python-certifi |
| idna | BSD-3-Clause | https://github.com/kjd/idna |
| charset-normalizer | MIT | https://github.com/jawah/charset_normalizer |
| protobuf | BSD-3-Clause | https://github.com/protocolbuffers/protobuf |
| FlatBuffers | Apache-2.0 | https://github.com/google/flatbuffers |
| pyclipper | MIT | https://github.com/fonttools/pyclipper |
| Shapely | BSD-3-Clause | https://github.com/shapely/shapely |
| PyYAML | MIT | https://github.com/yaml/pyyaml |
| six | MIT | https://github.com/benjaminp/six |
| tqdm | MPL-2.0 与 MIT | https://github.com/tqdm/tqdm |
| packaging | Apache-2.0 或 BSD-2-Clause | https://github.com/pypa/packaging |
| PyInstaller（仅用于构建） | GPL-2.0-or-later，附打包例外 | https://github.com/pyinstaller/pyinstaller |

## 特别说明

- **pystray（LGPL-3.0）**：免安装版以动态打包形式包含该库。根据 LGPL 的要求，
  本项目的全部源码与构建脚本均公开在
  https://github.com/pubobaji-hyx/screen-translator ，
  你可以自行替换 pystray 后重新构建。
- **OCR 模型**：RapidOCR 随包提供的 PP-OCR 模型版权归 PaddleOCR / 百度所有，
  按其 Apache-2.0 许可证分发。
