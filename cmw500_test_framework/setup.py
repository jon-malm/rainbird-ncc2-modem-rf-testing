#!/usr/bin/env python3
"""Setup script for CMW500 Test Framework."""

from setuptools import setup, find_packages
from pathlib import Path

# Read README for long description
readme_path = Path(__file__).parent / "README.md"
long_description = ""
if readme_path.exists():
    long_description = readme_path.read_text(encoding="utf-8")

setup(
    name="cmw500-test-framework",
    version="0.1.0",
    author="RF Testing Team",
    description="Python test framework for R&S CMW500 network simulation and RF testing",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/your-org/cmw500-test-framework",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Scientific/Engineering",
        "Topic :: Software Development :: Testing",
    ],
    python_requires=">=3.8",
    install_requires=[
        # Core has no required dependencies (uses stdlib only)
    ],
    extras_require={
        "yaml": ["pyyaml>=5.0"],
        "dev": [
            "pytest>=7.0",
            "pytest-cov>=4.0",
            "mypy>=1.0",
            "black>=23.0",
            "flake8>=6.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "cmw500-cli=cmw500_test_framework.cli:main",
        ],
    },
    include_package_data=True,
    package_data={
        "cmw500_test_framework": [
            "configs/examples/*.yaml",
        ],
    },
)
