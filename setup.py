"""Python setup.py for crypto_trading_engine package"""
import io
import os
from setuptools import find_packages, setup


def read(*paths, **kwargs):
    """Read the contents of a text file safely.
    >>> read("crypto_trading_engine", "VERSION")
    '0.1.0'
    >>> read("README.md")
    ...
    """

    content = ""
    with io.open(
        os.path.join(os.path.dirname(__file__), *paths),
        encoding=kwargs.get("encoding", "utf8"),
    ) as open_file:
        content = open_file.read().strip()
    return content


def read_requirements(path):
    return [
        line.strip()
        for line in read(path).split("\n")
        if not line.startswith(('"', "#", "-", "git+"))
    ]


setup(
    name="crypto_trading_engine",
    version=read("crypto_trading_engine", "VERSION"),
    description="Awesome crypto_trading_engine created by zhanghaowx",
    url="https://github.com/zhanghaowx/crypto-trading-engine/",
    long_description=read("README.md"),
    long_description_content_type="text/markdown",
    author="zhanghaowx",
    packages=find_packages(exclude=["tests", ".github"]),
    install_requires=read_requirements("requirements.txt"),
    entry_points={
        "console_scripts": ["crypto_trading_engine = crypto_trading_engine.__main__:main"]
    },
    extras_require={"test": read_requirements("requirements-test.txt")},
)
