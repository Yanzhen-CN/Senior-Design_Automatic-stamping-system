# 环境配置与运行说明

在项目根目录运行下面两个脚本即可：

```cmd
cd /d D:\Personal\Desktop\SD\Automatic-stamping-system
```

## 1. 配置环境

第一次运行，或依赖更新后运行：

```cmd
scripts\setup_env.bat
```

作用：

- 创建或更新 conda 环境 `SD`
- 按 `environment.yml` 安装 Python 依赖
- 安装项目运行所需的本地包

## 2. 启动应用

环境配置完成后运行：

```cmd
scripts\run_app.bat
```

作用：

- 使用 conda 环境 `SD`
- 启动桌面版盖章机控制界面

如果只是调试网页版本，也可以运行：

```cmd
scripts\run_web.bat
```

然后在浏览器打开：

```text
http://127.0.0.1:8000
```

