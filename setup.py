from setuptools import setup, find_packages

setup(
    name="csvwise",
    version="0.1.0",
    description="🧠 AI-Powered CSV Data Analyst - 用自然语言分析你的数据",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    author="Karl Yang",
    author_email="karl@example.com",
    url="https://github.com/yxjsxy/csvwise",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    py_modules=["csvwise"],
    python_requires=">=3.9",
    install_requires=[],  # Only stdlib - gemini CLI is external
    extras_require={
        "viz": ["matplotlib", "pandas"],
        "full": ["matplotlib", "pandas", "tabulate"],
    },
    entry_points={
        "console_scripts": [
            "csvwise=csvwise:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: Information Analysis",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
    ],
)
