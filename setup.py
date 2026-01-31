#!/usr/bin/env python3
"""
Setup script for SwayBG+ - Advanced Multi-Monitor Background Manager for Sway
"""

import os
import sys
from setuptools import setup, find_packages

# Read the README file for long description
def read_readme():
    """Read README.md for long description"""
    try:
        with open("README.md", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "Advanced multi-monitor background manager for Sway with screen orientation support"

# Read version from a version file or set default
def get_version():
    """Get version from __version__.py or default"""
    try:
        with open("__version__.py", "r") as f:
            version_dict = {}
            exec(f.read(), version_dict)
            return version_dict['__version__']
    except FileNotFoundError:
        return "1.0.0"

# Check Python version
if sys.version_info < (3, 6):
    print("Error: SwayBG+ requires Python 3.6 or later.")
    sys.exit(1)

# Check if we're on a supported platform
if sys.platform not in ['linux', 'linux2']:
    print("Warning: SwayBG+ is designed for Linux systems with Sway window manager.")

setup(
    name="swaybgplus",
    version=get_version(),
    author="SwayBG+ Contributors",
    author_email="dev@neotec.dev",
    description="Sway Background and Screen Manager",
    long_description=read_readme(),
    long_description_content_type="text/markdown",
    url="https://github.com/neotecdigital/swaybgplus",
    project_urls={
        "Bug Reports": "https://github.com/neotecdigital/swaybgplus/issues",
        "Source": "https://github.com/neotecdigital/swaybgplus",
        "Documentation": "https://github.com/neotecdigital/swaybgplus/blob/main/README.md",
    },
    packages=find_packages(exclude=['backups', 'backups.*', 'build', 'build.*', '__pycache__']),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: X11 Applications :: GTK",
        "Environment :: Wayland",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Desktop Environment",
        "Topic :: Multimedia :: Graphics",
        "Topic :: System :: Systems Administration",
    ],
    keywords="sway wayland background wallpaper monitor multi-monitor orientation",
    python_requires=">=3.6",
    install_requires=[
        "Pillow>=7.0.0",
        "PyGObject>=3.30.0",
    ],
    extras_require={
        "dev": [
            "pytest>=6.0",
            "black>=21.0",
            "flake8>=3.8",
        ],
    },
    entry_points={
        "console_scripts": [
            "swaybgplus=swaybgplus_cli:main",
            "swaybgplus-cli=swaybgplus_cli:main",
            "swaybgplus-gui=swaybgplus_gui:main",
        ],
    },
    scripts=[
        "swaybgplus_cli.py",
        "swaybgplus_gui.py",
    ],
    data_files=[
        ("share/applications", ["swaybgplus.desktop"]),
        ("share/doc/swaybgplus", ["README.md"]),
        ("share/man/man1", ["swaybgplus.1"]) if os.path.exists("swaybgplus.1") else [],
    ],
    include_package_data=True,
    zip_safe=False,
    platforms=["linux"],
)

# Post-installation message
def post_install():
    print("\n" + "="*60)
    print("🎉 SwayBG+ installed successfully!")
    print("="*60)
    print("📱 CLI Usage:")
    print("   swaybgplus image.jpg --mode stretched")
    print("   swaybgplus --orientation DP-1:90")
    print()
    print("🖥️  GUI Usage:")
    print("   swaybgplus-gui")
    print()
    print("📖 Documentation:")
    print("   man swaybgplus")
    print("   /usr/share/doc/swaybgplus/README.md")
    print()
    print("🔧 First time setup:")
    print("   1. Make sure Sway and swaybg are installed")
    print("   2. Run: swaybgplus-gui to configure monitors")
    print("   3. Load an image and apply backgrounds")
    print("="*60)

if __name__ == "__main__":
    setup()
    if "install" in sys.argv:
        post_install() 