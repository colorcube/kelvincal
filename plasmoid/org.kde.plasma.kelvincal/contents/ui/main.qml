import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.plasma5support as P5Support
import org.kde.kirigami as Kirigami

PlasmoidItem {
    id: root
    preferredRepresentation: compactRepresentation

    property string activePreset: ""
    property var presetList: []
    property bool isBusy: false
    property bool isDe: Qt.locale().name.indexOf("de") === 0

    toolTipMainText: "KelvinCal"
    toolTipSubText: activePreset.length > 0
        ? (isDe ? "Aktives Preset: " + activePreset : "Active preset: " + activePreset)
        : (isDe ? "Display-Preset auswählen" : "Select display preset")

    onExpandedChanged: {
        if (expanded) {
            reloadPresets()
        }
    }

    P5Support.DataSource {
        id: executable
        engine: "executable"
        connectedSources: []
        onNewData: function(sourceName, data) {
            var stdout = data["stdout"] || ""
            disconnectSource(sourceName)
            root.isBusy = false
            if (sourceName.indexOf("list-presets --json") !== -1 && stdout.trim().length > 0) {
                try {
                    var parsed = JSON.parse(stdout)
                    root.activePreset = parsed.active_preset || ""
                    root.presetList = parsed.presets || []
                } catch (e) {
                    console.warn("KelvinCal JSON Parse Error:", e)
                }
            } else if (sourceName.indexOf("apply-preset") !== -1) {
                root.reloadPresets()
            }
        }
    }

    function reloadPresets() {
        executable.connectSource('PATH="$HOME/.local/bin:$PATH" kcal-cli list-presets --json')
    }

    function applyPreset(presetName) {
        root.isBusy = true
        root.activePreset = presetName
        var escaped = presetName.replace(/"/g, '\\"')
        executable.connectSource('PATH="$HOME/.local/bin:$PATH" kcal-cli apply-preset "' + escaped + '"')
    }

    function openCalibratorGui() {
        executable.connectSource('PATH="$HOME/.local/bin:$PATH" kcal-gui &')
    }

    Component.onCompleted: {
        reloadPresets()
    }

    fullRepresentation: Item {
        Layout.preferredWidth: Kirigami.Units.gridUnit * 19
        Layout.preferredHeight: Kirigami.Units.gridUnit * 15

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: Kirigami.Units.smallSpacing
            spacing: Kirigami.Units.smallSpacing

            RowLayout {
                Layout.fillWidth: true
                Kirigami.Heading {
                    level: 4
                    text: root.isDe ? "KelvinCal Display-Presets" : "KelvinCal Display Presets"
                    Layout.fillWidth: true
                }
                PlasmaComponents3.BusyIndicator {
                    running: root.isBusy
                    visible: root.isBusy
                    Layout.preferredWidth: Kirigami.Units.iconSizes.small
                    Layout.preferredHeight: Kirigami.Units.iconSizes.small
                }
                PlasmaComponents3.ToolButton {
                    icon.name: "view-refresh"
                    onClicked: root.reloadPresets()
                    PlasmaComponents3.ToolTip {
                        text: root.isDe ? "Presets neu laden" : "Refresh presets"
                    }
                }
            }

            ListView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                model: root.presetList
                delegate: PlasmaComponents3.ItemDelegate {
                    width: ListView.view.width
                    highlighted: modelData.name === root.activePreset
                    contentItem: RowLayout {
                        PlasmaComponents3.RadioButton {
                            checked: modelData.name === root.activePreset
                            onClicked: root.applyPreset(modelData.name)
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2
                            PlasmaComponents3.Label {
                                text: modelData.name
                                font.bold: modelData.name === root.activePreset
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }
                            PlasmaComponents3.Label {
                                text: (modelData.displays ? modelData.displays.length : 0) + (root.isDe ? " Monitore (DDC + ICC)" : " displays (DDC + ICC)")
                                opacity: 0.7
                                font.pointSize: Kirigami.Theme.smallFont.pointSize
                            }
                        }
                    }
                    onClicked: root.applyPreset(modelData.name)
                }
            }

            PlasmaComponents3.Button {
                Layout.fillWidth: true
                icon.name: "preferences-desktop-display-color"
                text: root.isDe ? "KelvinCal Kalibrierung öffnen..." : "Open KelvinCal Calibrator..."
                onClicked: root.openCalibratorGui()
            }
        }
    }
}
