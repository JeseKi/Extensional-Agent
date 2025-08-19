#!/usr/bin/env python3
"""
ExtensionalAgent SDK 安装配置文件

用于将模块打包分发为 Python 包，支持通过 pip 安装使用。
"""

from setuptools import setup, find_packages
from pathlib import Path

# 读取 README 文件作为长描述
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text(encoding='utf-8') if (this_directory / "README.md").exists() else ""

# 直接定义依赖，避免从 requirements.txt 读取复杂格式
install_requires = [
    "pydantic>=2.11.7",
]

setup(
    name="extensional_agent",
    version="0.1.0",
    author="Jese__Ki",
    author_email="2094901072@qq.com",
    description="基于 Agent 的可扩展框架 SDK",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Jese__Ki/extensional_agent",
    packages=find_packages(exclude=["tests*", "examples*"]),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Security",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    python_requires=">=3.8",
    install_requires=install_requires,
    extras_require={
        "dev": [
            "pip-tools==7.5.0",
            "pydantic==2.11.7",
            "pytest==8.4.1",
            "pytest-cov==6.2.1",
            "pytest-mock==3.14.1",
            "pytest-asyncio==1.1.0",
        ]
    },
    entry_points={
        "console_scripts": [
            # 如果需要命令行工具，可以在这里添加
        ],
    },
    include_package_data=True,
    package_data={
        "extensional_agent": ["py.typed"],
    },
    zip_safe=False,
    keywords="agent security penetration-testing sdk framework",
    project_urls={
        "Bug Reports": "https://github.com/your-username/extensional_agent/issues",
        "Source": "https://github.com/your-username/extensional_agent",
        "Documentation": "https://extensional_agent.readthedocs.io/",
    },
)