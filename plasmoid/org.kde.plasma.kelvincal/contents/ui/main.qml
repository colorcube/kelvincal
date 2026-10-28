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

    P5Support.DataSource {
        id: executable
        engine: "executable"
        connectedSources: []
        onNewData: function(sourceName, data) {
            var stdout = data["stdout"] || ""
            disconnectSource(sourceName)
            if (sourceName.indexOf("list-presets --json") !== -1 && stdout.trim().length > 0) {
                try {
                    var parsed = JSON.parse(stdout)
                    root.activePreset = parsed.active_preset || ""
                    root.presetList = parsed.presets || []
                } catch (e) {
                    console.warn("KelvinCal JSON Parse Error:", e)
                }
            } else {
                root.reloadPresets()
            }
        }
    }

    function reloadPresets() {
        executable.connectSource("kcal-cli list-presets --json")
    }

    function applyPreset(presetName) {
        var escaped = presetName.replace(/"/g, '\\"')
        executable.connectSource('kcal-cli apply-preset "' + escaped + '"')
    }

    function openCalibratorGui() {
        executable.connectSource("kcal-gui")
    }

    Component.onCompleted: {
        reloadPresets()
    }

    fullRepresentation: Item {
        Layout.preferredWidth: Kirigami.Units.gridUnit * 18
        Layout.preferredHeight: Kirigami.Units.gridUnit * 14

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: Kirigami.Units.smallSpacing
            spacing: Kirigami.Units.smallSpacing

            RowLayout {
                Layout.fillWidth: true
                Kirigami.Heading {
                    level: 4
                    text: "KelvinCal Display Presets"
                    Layout.fillWidth: true
                }
                PlasmaComponents3.ToolButton {
                    icon.name: "view-refresh"
                    onClicked: root.reloadPresets()
                    PlasmaComponents3.ToolTip { text: "Refresh presets" }
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
                                text: (modelData.displays ? modelData.displays.length : 0) + " displays (DDC + ICC)"
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
                text: "Open KelvinCal Calibrator..."
                onClicked: root.openCalibratorGui()
            }
        }
    }
}
