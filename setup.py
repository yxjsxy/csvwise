from setuptools import setup, find_packages

with open("README.md", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="csvwise",
    version="0.1.0",
    description="🧠 AI-Powered CSV Data Analyst - 用自然语言分析你的数据",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Karl Yang",
    url="https://github.com/yxjsxy/csvwise",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    py_modules=["csvwise", "db_connector"],
    python_requires=">=3.9",
    install_requires=[
        "requests",
    ],
    extras_require={
        "web": ["streamlit", "pandas", "matplotlib"],
        "db": ["psycopg2-binary"],
        "excel": ["openpyxl", "xlrd"],
        "full": ["streamlit", "pandas", "matplotlib", "psycopg2-binary", "openpyxl", "xlrd", "tabulate"],
    },
    entry_points={
        "console_scripts": [
            "csvwise=csvwise:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: Information Analysis",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    keywords="csv data analysis ai llm natural-language pandas sqlite postgresql",
    project_urls={
        "Bug Reports": "https://github.com/yxjsxy/csvwise/issues",
        "Source": "https://github.com/yxjsxy/csvwise",
    },
)
