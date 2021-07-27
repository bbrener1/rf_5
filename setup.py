import setuptools
from pathlib import Path
from setuptools.command.install import install
from subprocess import check_call
from distutils.core import Extension

class PostInstallCommand(install):
    """Post-installation for installation mode."""
    def run(self):
        path = str((Path(__file__).parent).resolve())
        print(f"Building binary at {path}")
        check_call('pwd'.split())
        check_call('ls'.split())
        check_call(["bash", "./recipe/py_build.sh",path])
        install.run(self)


with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

    setuptools.setup(
        name="rusty-axe-bbrener1",
        version="0.5",
        author="Boris Brenerman",
        author_email="bbrener1@jhu.edu",
        description="Random Forest Latent Structure (Biology)",
        long_description=long_description,
        long_description_content_type="text/markdown",
        url="https://github.com/bbrener1/rf_5",
        project_urls={
            "Bug Tracker": "https://github.com/bbrener1/rf_5/issues",
        },
        classifiers=[
            "Programming Language :: Python :: 3",
            "License :: OSI Approved :: MIT License",
            "Operating System :: MacOS :: MacOS X",
            "Operating System :: POSIX",
            "Programming Language :: Rust",
            "Topic :: Scientific/Engineering :: Bio-Informatics",
        ],
        packages=['rusty_axe'],
        package_dir={
            "rusty_axe": "rusty_axe",
        },
        # include_package_data=True,
        # package_data={
        #     "rusty_axe":["src/*.rs",]
        # },
        package_data={
            "rusty_axe":["./bin/*",]
        },
        cmdclass={
            'install': PostInstallCommand,
        },
        install_requires=[
            'scanpy',
            'leidenalg',
            'scikit-learn',
            'matplotlib>=3.4.2'
        ],
        python_requires="<3.9",
    )
