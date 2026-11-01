#!/usr/bin/env bash
# Builds the KelvinCal rpm (and src.rpm) from a git revision.
#
#   packaging/rpm/build.sh [REVISION]          # in a Fedora container (podman or docker), default HEAD
#   KELVINCAL_RPM_NATIVE=1 packaging/rpm/build.sh   # directly, e.g. inside the CI container
#
# Results: dist/rpm/*.rpm
set -euo pipefail
ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../.." && pwd)"
REV="${1:-HEAD}"
FEDORA="${FEDORA_RELEASE:-44}"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "${ROOT}/packages/kelvincal/__init__.py")"
OUT="${ROOT}/dist/rpm"

if [[ "${KELVINCAL_RPM_NATIVE:-}" != 1 ]]; then
    engine="$(command -v podman || command -v docker)" || { echo "podman or docker needed" >&2; exit 1; }
    mkdir -p "${OUT}"
    git -C "${ROOT}" archive --format=tar.gz --prefix="kelvincal-${VERSION}/" -o "${OUT}/kelvincal-${VERSION}.tar.gz" "${REV}"
    exec "${engine}" run --rm -v "${ROOT}:/src:Z" -e KELVINCAL_RPM_NATIVE=1 -e KELVINCAL_TARBALL_READY=1 \
        "registry.fedoraproject.org/fedora:${FEDORA}" /src/packaging/rpm/build.sh
fi

dnf -y -q install rpm-build dnf-plugins-core git-core >/dev/null
TOP="$(mktemp -d)"
mkdir -p "${TOP}/SOURCES" "${OUT}"
if [[ "${KELVINCAL_TARBALL_READY:-}" == 1 ]]; then
    cp "${OUT}/kelvincal-${VERSION}.tar.gz" "${TOP}/SOURCES/"
else
    git -C "${ROOT}" archive --format=tar.gz --prefix="kelvincal-${VERSION}/" \
        -o "${TOP}/SOURCES/kelvincal-${VERSION}.tar.gz" "${REV}"
fi
SPEC="${ROOT}/packaging/rpm/kelvincal.spec"
grep -q "^Version: *${VERSION}$" "${SPEC}" || { echo "kelvincal.spec Version differs from ${VERSION}" >&2; exit 1; }

dnf -y -q builddep "${SPEC}" >/dev/null
# %generate_buildrequires: install what the build backend asks for, then build
for _ in 1 2 3; do
    rc=0
    rpmbuild -br --define "_topdir ${TOP}" "${SPEC}" >/dev/null 2>&1 || rc=$?
    [[ ${rc} -eq 11 ]] || break
    dnf -y -q builddep "${TOP}"/SRPMS/*.buildreqs.nosrc.rpm >/dev/null
    rm -f "${TOP}"/SRPMS/*.buildreqs.nosrc.rpm
done
rpmbuild -ba --define "_topdir ${TOP}" "${SPEC}"
cp "${TOP}"/RPMS/noarch/*.rpm "${TOP}"/SRPMS/*.src.rpm "${OUT}/"
ls -l "${OUT}"
