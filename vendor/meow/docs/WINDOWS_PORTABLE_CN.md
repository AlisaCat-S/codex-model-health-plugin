# meow4.5.3 · Windows便携版

适用Windows10/11，Intel/AMD x64。包内有独立Python及依赖，无需安装Python或设置PATH。

1. 完整解压文件名包含windows-x64-portable-zh-CN.zip的包到新可写目录。
2. 双击start.bat。不要在压缩包内运行，也不要删除python文件夹。
3. 浏览器未打开时访问 http://127.0.0.1:8765/；可用 `start.bat --port 8794` 指定端口。

与源码版使用相同评分、基准及更新流程。程序内点击更新后，会准备新版、等待当前任务完成、自动重启；失败时恢复旧版。4.5.2首次进入4.5.3，先结束旧后台，再运行新启动器，可用--migrate-from迁移旧目录。原数据不删除，系统凭据引用不会把Key复制到另一台电脑。

关闭浏览器不等于停止后台。结束检测并暂停计划后，可在设置中点击“停止本地服务”；再次运行原start.bat会打开当前安装版本。报告保存在meow_runs，自动更新不重算旧报告。

Python版本、依赖与摘要见PORTABLE_BUILD.json；校验清单为SHA256SUMS.txt，Python许可在python/LICENSE.txt，依赖许可随.dist-info目录保留。源码安装步骤见README_SOURCE_CN.md，统计限制见TECHNICAL_REPORT_CN.md。
