@echo off
echo ========================================
echo 腹膜透析优化系统 - 完整修复脚本
echo ========================================

cd /d D:\OneDrive\Desktop\大三上网安\大创\pd_simulator

echo.
echo [1/5] 创建__init__.py文件...
cd backend
type nul > __init__.py
cd models
type nul > __init__.py
cd ..\optimizer
type nul > __init__.py
cd ..\api
type nul > __init__.py
cd ..\utils
type nul > __init__.py
cd ..\..
echo ✓ __init__.py文件创建完成

echo.
echo [2/5] 激活Python虚拟环境...
cd backend
if not exist "venv" (
    echo   创建虚拟环境...
    python -m venv venv
)
call venv\Scripts\activate
echo ✓ 虚拟环境已激活

echo.
echo [3/5] 安装Python依赖...
pip install -q flask==2.3.0 flask-cors==4.0.0 numpy==1.24.0 matplotlib==3.7.0 scipy==1.10.0
echo ✓ Python依赖安装完成

echo.
echo [4/5] 安装前端依赖...
cd ..\frontend
if not exist "node_modules" (
    npm config set registry https://registry.npmmirror.com
    npm install
)
echo ✓ 前端依赖安装完成

echo.
echo [5/5] 验证安装...
cd ..\backend
python -c "from models.parameters import ModelParameters; print('✓ Python模块导入成功')"

cd ..\frontend
if exist "node_modules\vue" (
    echo ✓ Vue安装成功
) else (
    echo ✗ Vue安装失败
)

echo.
echo ========================================
echo 修复完成！
echo ========================================
echo.
echo 启动后端: cd backend ^& venv\Scripts\activate ^& python api/app.py
echo 启动前端: cd frontend ^& npm run dev
echo.
pause
