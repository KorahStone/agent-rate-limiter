from setuptools import setup, find_packages

setup(
    name="agent-rate-limiter",
    version="0.1.0",
    description="Intelligent rate limiting and cost management for AI agents",
    author="Korah Stone",
    author_email="korahcomm@gmail.com",
    url="https://github.com/KorahStone/agent-rate-limiter",
    packages=find_packages(),
    install_requires=[
        "httpx>=0.25.0",
        "pydantic>=2.0.0",
        "tenacity>=8.2.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-asyncio>=0.21.0",
            "pytest-cov>=4.1.0",
        ]
    },
    python_requires=">=3.10",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)
