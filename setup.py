from setuptools import find_packages, setup

setup(
    name="source_hubble",
    description="Source connector for Hubble API (data2apis.com)",
    author="Cazou Vilela",
    author_email="cazou@hubtalent.com.br",
    packages=find_packages(),
    install_requires=[
        "airbyte-cdk>=0.50.0",
        "requests>=2.28.0",
    ],
    package_data={"": ["*.yaml"]},
)
