Name:           kelvincal
Version:        0.1.0
Release:        1%{?dist}
Summary:        Display calibration for KDE Plasma: DDC/CI hardware adjustment and ArgyllCMS profiling

License:        GPL-3.0-or-later
URL:            https://github.com/colorcube/kelvincal
Source0:        %{url}/archive/v%{version}/%{name}-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  python3-devel
BuildRequires:  pyproject-rpm-macros
BuildRequires:  desktop-file-utils
BuildRequires:  libappstream-glib
# %%check: the test suite runs offscreen
BuildRequires:  python3-pyside6
BuildRequires:  qt6-qtbase-gui

Requires:       python3-pyside6
Requires:       argyllcms
Requires:       ddcutil
# kscreen-doctor
Requires:       libkscreen
Requires:       hicolor-icon-theme
Recommends:     %{name}-plasmoid = %{version}-%{release}
Recommends:     colord

%description
KelvinCal calibrates displays under KDE Plasma on Wayland. It sets the white
point and brightness in the display's own hardware over DDC/CI, measures an
ICC profile with ArgyllCMS and activates it in KWin. Presets switch brightness,
contrast, RGB gains and ICC profile of all displays at once.

%package plasmoid
Summary:        KelvinCal preset switcher for the Plasma panel
Requires:       %{name} = %{version}-%{release}
Requires:       plasma-workspace

%description plasmoid
Panel widget that switches KelvinCal display presets with one click and warns
when a display no longer matches the active preset.

%prep
%autosetup -n %{name}-%{version}

%generate_buildrequires
%pyproject_buildrequires

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files kelvincal

install -Dpm 0644 share/applications/de.colorcube.kelvincal.desktop \
    %{buildroot}%{_datadir}/applications/de.colorcube.kelvincal.desktop
install -Dpm 0644 share/metainfo/de.colorcube.kelvincal.metainfo.xml \
    %{buildroot}%{_metainfodir}/de.colorcube.kelvincal.metainfo.xml
install -Dpm 0644 share/knotifications6/kelvincal.notifyrc \
    %{buildroot}%{_datadir}/knotifications6/kelvincal.notifyrc
for size in scalable 16x16 22x22 symbolic; do
    install -Dpm 0644 -t %{buildroot}%{_datadir}/icons/hicolor/$size/apps share/icons/hicolor/$size/apps/*.svg
done
mkdir -p %{buildroot}%{_datadir}/plasma/plasmoids
cp -a plasmoid/de.colorcube.kelvincal.applet %{buildroot}%{_datadir}/plasma/plasmoids/

%check
desktop-file-validate %{buildroot}%{_datadir}/applications/de.colorcube.kelvincal.desktop
appstream-util validate-relax --nonet %{buildroot}%{_metainfodir}/de.colorcube.kelvincal.metainfo.xml
QT_QPA_PLATFORM=offscreen PYTHONPATH=%{buildroot}%{python3_sitelib} %{python3} -m unittest discover -s tests

%files -f %{pyproject_files}
%license LICENSE
%doc README.md CHANGELOG.md
%{_bindir}/kelvincal
%{_bindir}/kelvincal-cli
%{_datadir}/applications/de.colorcube.kelvincal.desktop
%{_metainfodir}/de.colorcube.kelvincal.metainfo.xml
%{_datadir}/knotifications6/kelvincal.notifyrc
%{_datadir}/icons/hicolor/*/apps/de.colorcube.kelvincal*.svg

%files plasmoid
%{_datadir}/plasma/plasmoids/de.colorcube.kelvincal.applet/

%changelog
* Sun Nov 01 2026 René Fritz <rf@colorcube.de> - 0.1.0-1
- First release
