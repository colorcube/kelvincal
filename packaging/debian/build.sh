#!/usr/bin/env bash
# Builds the KelvinCal deb packages from a git revision.
#
#   packaging/debian/build.sh [REVISION]              # in a Debian container (podman or docker), default HEAD
#   KELVINCAL_DEB_NATIVE=1 packaging/debian/build.sh  # directly, e.g. inside the CI container
#
# Results: dist/deb/*.deb
set -euo pipefail
ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../.." && pwd)"
REV="${1:-HEAD}"
DEBIAN="${DEBIAN_RELEASE:-trixie}"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "${ROOT}/packages/kelvincal/__init__.py")"
OUT="${ROOT}/dist/deb"
ORIG="kelvincal_${VERSION}.orig.tar.gz"

head -1 "${ROOT}/packaging/debian/changelog" | grep -q "(${VERSION}-" \
    || { echo "debian/changelog version differs from ${VERSION}" >&2; exit 1; }

if [[ "${KELVINCAL_DEB_NATIVE:-}" != 1 ]]; then
    engine="$(command -v podman || command -v docker)" || { echo "podman or docker needed" >&2; exit 1; }
    mkdir -p "${OUT}"
    git -C "${ROOT}" archive --format=tar.gz --prefix="kelvincal-${VERSION}/" -o "${OUT}/${ORIG}" "${REV}"
    exec "${engine}" run --rm -v "${ROOT}:/src:Z" -e KELVINCAL_DEB_NATIVE=1 -e KELVINCAL_TARBALL_READY=1 \
        "docker.io/library/debian:${DEBIAN}" /src/packaging/debian/build.sh
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends build-essential devscripts equivs git ca-certificates >/dev/null
WORK="$(mktemp -d)"
mkdir -p "${OUT}"
if [[ "${KELVINCAL_TARBALL_READY:-}" == 1 ]]; then
    cp "${OUT}/${ORIG}" "${WORK}/"
else
    git -C "${ROOT}" archive --format=tar.gz --prefix="kelvincal-${VERSION}/" -o "${WORK}/${ORIG}" "${REV}"
fi
tar -xzf "${WORK}/${ORIG}" -C "${WORK}"
SRC="${WORK}/kelvincal-${VERSION}"
cp -a "${ROOT}/packaging/debian" "${SRC}/debian"
chmod +x "${SRC}/debian/rules"
(cd "${SRC}" && mk-build-deps -i -r -t "apt-get -y -qq --no-install-recommends" debian/control >/dev/null)
(cd "${SRC}" && dpkg-buildpackage -us -uc -b)
cp "${WORK}"/*.deb "${OUT}/"
rm -f "${OUT}/${ORIG}"
ls -l "${OUT}"
