# Maintainer: Your Name <your.email@example.com>
pkgname=swaybgplus
pkgver=1.0.0
pkgrel=1
pkgdesc="Advanced multi-monitor background manager for Sway with screen orientation support"
arch=('any')
url="https://github.com/alephpt/swaybgplus"
license=('Ancillary')
depends=(
    'python'
    'python-pillow'
    'python-gobject'
    'gtk3'
    'sway'
    'swaybg'
)
makedepends=('python-setuptools')
optdepends=(
    'python-pip: for additional Python package management'
)
source=("$pkgname-$pkgver.tar.gz::$url/archive/v$pkgver.tar.gz")
sha256sums=('SKIP')  # Update this with actual checksum when releasing

build() {
    cd "$pkgname-$pkgver"
    python setup.py build
}

package() {
    cd "$pkgname-$pkgver"
    
    # Install Python package
    python setup.py install --root="$pkgdir" --optimize=1 --skip-build
    
    # Install scripts to /usr/bin
    install -Dm755 swaybgplus_cli.py "$pkgdir/usr/bin/swaybgplus-cli"
    install -Dm755 swaybgplus_gui.py "$pkgdir/usr/bin/swaybgplus-gui"
    
    # Create symbolic links for easier access
    install -d "$pkgdir/usr/bin"
    ln -sf swaybgplus-cli "$pkgdir/usr/bin/swaybgplus"
    
    # Install desktop file
    install -Dm644 swaybgplus.desktop "$pkgdir/usr/share/applications/swaybgplus.desktop"
    
    # Install documentation
    install -Dm644 README.md "$pkgdir/usr/share/doc/$pkgname/README.md"
    install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
    
    # Install man pages if they exist
    if [ -f "swaybgplus.1" ]; then
        install -Dm644 swaybgplus.1 "$pkgdir/usr/share/man/man1/swaybgplus.1"
    fi
    
    # Install icon if it exists
    if [ -f "swaybgplus.png" ]; then
        install -Dm644 swaybgplus.png "$pkgdir/usr/share/pixmaps/swaybgplus.png"
    fi
} 