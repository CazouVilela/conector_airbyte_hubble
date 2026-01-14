from setuptools import find_packages, setup

MAIN_REQUIREMENTS = [
    "airbyte-cdk>=7.0.0,<8.0.0",
    "requests>=2.28.0",
]

TEST_REQUIREMENTS = [
    "pytest>=7.0.0",
    "pytest-cov>=4.0.0",
    "pytest-mock>=3.10.0",
    "requests-mock>=1.11.0",
]

setup(
    name="source_hubble",
    version="1.0.0",
    description="Airbyte source connector for Hubble API (data2apis.com)",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Cazou Vilela",
    author_email="cazou@hubtalent.com.br",
    url="https://github.com/CazouVilela/conector_airbyte_hubble",
    packages=find_packages(exclude=["tests", "tests.*"]),
    install_requires=MAIN_REQUIREMENTS,
    extras_require={
        "tests": TEST_REQUIREMENTS,
    },
    package_data={"": ["*.yaml", "*.json"]},
    python_requires=">=3.10",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
    ],
)
