# bt-open-wifi-apis

Bituo SPM / SDM / SXM 电能表 **Open Wi-Fi API** 的对外接口文档 + 体验工具 + 机器可读清单。**私有仓库**，按需授权给合作方；不含固件源码。

线上入口：[SPM/SDM Open Wi-Fi API Overview](https://docs.bituo-technik.com/device-api/spm-sdm-open-wi-fi-api-overview)　|　组织与维护约定：[`REPO_ORGANIZATION.md`](REPO_ORGANIZATION.md)　|　AI 入口：[`AGENTS.md`](AGENTS.md)

## 我该读哪份文档？

先确认设备的蓝牙服务：**`A002` = 明文，`A003` = 加密**（同一台设备只有其中一种）。

| 你的设备 | 第 1 步：传输层（怎么连、怎么解锁 / 握手） | 第 2 步：业务层（发什么命令、读什么字段） | 参考实现 |
|----------|------------------------------------------|------------------------------------------|----------|
| **Basic / Basic+**（明文，`A002`） | [明文 BLE 接口说明](docs/ble-plaintext/ble-plaintext-api.zh-CN.md) · [EN](docs/ble-plaintext/ble-plaintext-api.en.md) | [业务命令参考](docs/ble-common/ble-business-api.zh-CN.md) · [EN](docs/ble-common/ble-business-api.en.md) | [`tools/ble-plaintext`](tools/ble-plaintext/) |
| **Lite / Pro**（加密，`A003`） | [加密 BLE 接口说明](docs/ble-secured/ble-secured-api.zh-CN.md) · [EN](docs/ble-secured/ble-secured-api.en.md)；密码学细节 [协议权威参考](docs/ble-secured/crypto-protocol.zh-CN.md) · [EN](docs/ble-secured/crypto-protocol.en.md) | 同上（两个通道共用） | [`tools/ble-secured`](tools/ble-secured/) |

两个 BLE 通道解开传输层之后的业务 JSON **完全一致**，所以业务命令只在 `docs/ble-common` 维护一份，见 [`REPO_ORGANIZATION.md` §3](REPO_ORGANIZATION.md)。

只想**让设备连上 Wi-Fi**：读所选传输层文档的"快速开始"，再用 [业务命令参考 §2](docs/ble-common/ble-business-api.zh-CN.md#2-wi-fi-配网业务命令)。想直接试：见下面"工具"。

## 目录

```text
docs/
  ble-common/       两个 BLE 通道共用的业务命令参考（zh-CN / en）
  ble-plaintext/    明文 BLE 传输层（A002）
  ble-secured/      加密 BLE 传输层（A003）+ 协议权威参考
  README.md         阅读路径    SUMMARY.md  Gitbook 目录
tools/              体验工具（网页 + Windows）
spec/               机器可读：命令清单、加密测试向量
scripts/            校验与单页合集生成
dist/               生成物（不入库）
```

## 工具

```bat
:: 明文 BLE，Windows
cd tools\ble-plaintext & py -3 -m pip install -r requirements.txt & py -3 ble_plain_gui.py

:: 加密 BLE，Windows
cd tools\ble-secured & py -3 -m pip install -r requirements.txt & py -3 ble_secured_gui.py
```

网页版（Chrome / Edge）和手机使用说明见 [`tools/README.md`](tools/README.md)。给客户用的加密网页是**单个文件** [`web-ble-secured-console.offline.html`](tools/ble-secured/web-ble-secured-console.offline.html)，放到任意 HTTPS 静态托管即可。

## 维护

| 命令 | 作用 |
|------|------|
| `py -3 scripts/check_docs.py` | 校验链接 / 锚点、中英章节对齐、`spec` 与文档命令集一致、无遗留占位符 |
| `py -3 scripts/check_test_vectors.py` · `node scripts/check_test_vectors.mjs` | 两份参考实现对加密测试向量的结果必须一致 |
| `py -3 scripts/build_bundles.py` | 生成 `dist/*.md` 单页合集（传输层 + 业务层 [+ 协议参考]），用于粘贴 Gitbook 或整份交给 AI |
| `py -3 tools/ble-secured/bundle_offline_html.py` | 改了加密网页后重新生成离线单文件 |

## 不要提交

`tools/ble-secured/ble_crypto_client_cache.json`（含 LTK）、任何真机 PIN / LTK / 密钥截图、固件源码。`.gitignore` 已排除缓存文件。
