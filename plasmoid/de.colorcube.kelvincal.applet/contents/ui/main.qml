import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.plasma5support as P5Support
import org.kde.kirigami as Kirigami

PlasmoidItem {
    id: root
    preferredRepresentation: compactRepresentation

    property string activePreset: ""
    property var presetList: []
    property var displayList: []
    property bool guiRunning: false
    property bool guiBusy: false
    property bool isBusy: false
    property string errorText: ""
    property bool isDe: Qt.locale().name.indexOf("de") === 0
    readonly property var driftingDisplays: displayList.filter(function(d) { return d.drift.length > 0 })
    readonly property string cli: 'PATH="$HOME/.local/bin:$PATH" kelvincal-cli '

    // monochrome panel symbol (recoloured like the Breeze icons); installed by bin/install-desktop
    Plasmoid.icon: "de.colorcube.kelvincal-symbolic"
    Plasmoid.status: driftingDisplays.length > 0 ? PlasmaCore.Types.NeedsAttentionStatus
                                                 : PlasmaCore.Types.ActiveStatus
    toolTipMainText: "KelvinCal"
    toolTipSubText: {
        var text = activePreset.length > 0
            ? (isDe ? "Aktives Preset: " : "Active preset: ") + activePreset
            : (isDe ? "Kein Preset aktiv" : "No active preset")
        if (driftingDisplays.length > 0) {
            text += "\n" + (isDe ? "Weicht ab: " : "Differs: ")
                + driftingDisplays.map(function(d) { return d.connector }).join(", ")
        }
        if (guiBusy) {
            text += "\n" + (isDe ? "Messung läuft" : "Measurement running")
        }
        return text
    }

    // Shell single quotes: nothing is interpreted inside '...'; embedded quotes are closed, escaped, reopened.
    function shellQuote(text) {
        return "'" + text.replace(/'/g, "'\\''") + "'"
    }

    onExpandedChanged: {
        if (expanded) {
            reload()
        }
    }

    P5Support.DataSource {
        id: executable
        engine: "executable"
        connectedSources: []
        onNewData: function(sourceName, data) {
            var stdout = data["stdout"] || ""
            var stderr = (data["stderr"] || "").trim()
            disconnectSource(sourceName)
            if (sourceName.indexOf("overview --json") !== -1) {
                try {
                    var parsed = JSON.parse(stdout)
                    root.activePreset = parsed.active_preset || ""
                    root.presetList = parsed.presets || []
                    root.displayList = parsed.displays || []
                    root.guiRunning = parsed.gui ? parsed.gui.running : false
                    root.guiBusy = parsed.gui ? parsed.gui.busy : false
                } catch (e) {
                    console.warn("KelvinCal JSON Parse Error:", e, stderr)
                }
            } else if (sourceName.indexOf("apply-preset") !== -1) {
                root.isBusy = false
                root.errorText = data["exit code"] !== 0 ? stderr : ""
                root.reload()
            }
        }
    }

    // keeps the drift state current while the plasmoid is on the panel (DDC reads take < 1 s)
    Timer {
        interval: root.expanded ? 15000 : 120000
        running: true
        repeat: true
        onTriggered: root.reload()
    }

    function reload() {
        executable.connectSource(cli + "overview --json")
    }

    function applyPreset(presetName) {
        root.isBusy = true
        root.errorText = ""
        root.activePreset = presetName
        executable.connectSource(cli + "apply-preset " + shellQuote(presetName))
    }

    // kelvincal hands the request to an already running window (D-Bus) or starts a new one
    function openGui(connector) {
        var args = connector ? " --display " + shellQuote(connector) : ""
        executable.connectSource('PATH="$HOME/.local/bin:$PATH" kelvincal' + args + ' &')
    }

    Component.onCompleted: reload()

    // one line per preset; the popup shows up to `visibleRows` of them without scrolling
    readonly property int visibleRows: 10
    readonly property int rowHeight: Math.round(Kirigami.Units.gridUnit * 1.8)

    fullRepresentation: Item {
        Layout.preferredWidth: Kirigami.Units.gridUnit * 19
        // exactly as high as its content: Plasma would otherwise keep a larger (remembered) popup size
        Layout.preferredHeight: column.implicitHeight + 2 * Kirigami.Units.smallSpacing
        Layout.minimumHeight: Layout.preferredHeight
        Layout.maximumHeight: Layout.preferredHeight

        ColumnLayout {
            id: column
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
                    onClicked: root.reload()
                    PlasmaComponents3.ToolTip {
                        text: root.isDe ? "Presets neu laden" : "Refresh presets"
                    }
                }
            }

            Kirigami.InlineMessage {
                Layout.fillWidth: true
                visible: root.guiBusy || root.errorText.length > 0
                type: root.errorText.length > 0 ? Kirigami.MessageType.Error : Kirigami.MessageType.Information
                text: root.errorText.length > 0 ? root.errorText
                    : (root.isDe ? "KelvinCal misst gerade – Presets lassen sich erst danach umschalten."
                                 : "KelvinCal is measuring – presets can be switched afterwards.")
            }

            // only when a display no longer matches the active preset (e.g. changed in its OSD)
            Kirigami.InlineMessage {
                Layout.fillWidth: true
                visible: root.driftingDisplays.length > 0 && !root.guiBusy && root.errorText.length === 0
                type: Kirigami.MessageType.Warning
                text: (root.isDe ? "Weicht vom Preset ab: " : "Differs from the preset: ")
                    + root.driftingDisplays.map(function(d) { return d.connector }).join(", ")
                actions: [
                    Kirigami.Action {
                        text: root.isDe ? "Erneut anwenden" : "Apply again"
                        icon.name: "view-refresh"
                        onTriggered: root.applyPreset(root.activePreset)
                    }
                ]
            }

            ListView {
                id: presetView
                Layout.fillWidth: true
                Layout.preferredHeight: Math.max(1, Math.min(count, root.visibleRows)) * root.rowHeight
                clip: true
                model: root.presetList
                delegate: PlasmaComponents3.ItemDelegate {
                    width: ListView.view.width
                    height: root.rowHeight
                    enabled: !root.guiBusy
                    highlighted: modelData.name === root.activePreset
                    contentItem: RowLayout {
                        PlasmaComponents3.RadioButton {
                            checked: modelData.name === root.activePreset
                            onClicked: root.applyPreset(modelData.name)
                        }
                        PlasmaComponents3.Label {
                            text: modelData.name
                            font.bold: modelData.name === root.activePreset
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                    }
                    PlasmaComponents3.ToolTip {
                        text: modelData.description || ""
                        visible: parent.hovered && text.length > 0
                    }
                    onClicked: root.applyPreset(modelData.name)
                }
            }

            PlasmaComponents3.Button {
                Layout.fillWidth: true
                icon.name: "de.colorcube.kelvincal"
                text: root.guiRunning ? (root.isDe ? "KelvinCal anzeigen" : "Show KelvinCal")
                                      : (root.isDe ? "KelvinCal öffnen …" : "Open KelvinCal…")
                onClicked: root.openGui("")
            }
        }
    }
}
