%if 0%{?suse_version}
%{!?dist:%global dist .opensuse}
%global pythons python3
%{?python_enable_dependency_generator}
%{!?_metainfodir:%global _metainfodir %{_datadir}/metainfo}
%endif

Name:           kelvincal
Version:        0.3.1
Release:        1%{?dist}
Summary:        Display calibration for KDE Plasma: DDC/CI hardware adjustment and ArgyllCMS profiling

License:        GPL-3.0-or-later
URL:            https://github.com/colorcube/kelvincal
Source0:        %{url}/archive/v%{version}/%{name}-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  desktop-file-utils
%if 0%{?suse_version}
BuildRequires:  appstream-glib
BuildRequires:  fdupes
BuildRequires:  python-rpm-macros
BuildRequires:  %{python_module base >= 3.11}
BuildRequires:  %{python_module pip}
BuildRequires:  %{python_module pyside6 >= 6.6}
BuildRequires:  %{python_module setuptools >= 68.0}
BuildRequires:  %{python_module wheel}
# %%check: the test suite runs offscreen
BuildRequires:  libQt6Gui6
%else
BuildRequires:  python3-devel
BuildRequires:  pyproject-rpm-macros
BuildRequires:  libappstream-glib
# %%check: the test suite runs offscreen
BuildRequires:  python3-pyside6
BuildRequires:  qt6-qtbase-gui
%endif

Requires:       python3-pyside6
Requires:       argyllcms
Requires:       ddcutil
# kscreen-doctor
%if 0%{?suse_version}
Requires:       libkscreen6-plugin
%else
Requires:       libkscreen
%endif
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
%if 0%{?suse_version}
Requires:       plasma6-workspace
%else
Requires:       plasma-workspace
%endif

%description plasmoid
Panel widget that switches KelvinCal display presets with one click and warns
when a display no longer matches the active preset.

%prep
%autosetup -n %{name}-%{version}

%if !0%{?suse_version}
%generate_buildrequires
%pyproject_buildrequires
%endif

%build
%pyproject_wheel

%install
%pyproject_install
%if 0%{?suse_version}
%fdupes %{buildroot}%{python3_sitelib}
%else
%pyproject_save_files kelvincal
%endif

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
export QT_QPA_PLATFORM=offscreen
%if 0%{?suse_version}
%pyunittest discover -s tests
%else
PYTHONPATH=%{buildroot}%{python3_sitelib} %{python3} -m unittest discover -s tests
%endif

%if 0%{?suse_version}
%files
%{python3_sitelib}/kelvincal
%{python3_sitelib}/kelvincal-%{version}.dist-info
%else
%files -f %{pyproject_files}
%endif
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
* Sat Nov 21 2026 René Fritz <rf@colorcube.de> - 0.3.1-1
- Apply ICC Bradford chromatic adaptation in verification for D50 and custom whitepoints, fix Simple Mode batch workflow selection, tune default dispcal quality to -ql, guard preset watcher during activation, and complete German translations

* Sat Nov 21 2026 René Fritz <rf@colorcube.de> - 0.3.0-1
- Live gamma 2.2 / IEC sRGB verification switch and optional BPC, KWin Night Light and software dimming guard, observer-adapted whitepoints, dispcal -qm, and DDC/CI bounds/rollback hardening

* Fri Nov 20 2026 René Fritz <rf@colorcube.de> - 0.2.2-1
- Apply 1D software calibration curves (dispread -K) during patch measurement and outlier re-measurement, stabilise dark-patch outlier check, and increase spotread timeouts for slower colorimeters

* Thu Nov 19 2026 René Fritz <rf@colorcube.de> - 0.2.1-1
- DDC/CI gain scaling for 0-255-register panels, openSUSE Tumbleweed RPM support, and PySide6 6.12 shutdown fix

* Tue Nov 17 2026 René Fritz <rf@colorcube.de> - 0.2.0-1
- Software calibration (vcgt) with interactive display adjustment, profile-only workflow, patch presets, CIE 2015 observer, and Shaper + Matrix profiles

* Sun Nov 01 2026 René Fritz <rf@colorcube.de> - 0.1.0-1
- First release
