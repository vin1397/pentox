import QtQuick
import QtQuick.Layouts
import Quickshell

// Pentox taskbar chip for quickshell — mirrors the built-in layer-shell pill.
// Shows a lavender pill while a game session is active, with game name and
// live FPS. Reads the state file the watcher writes; FPS comes straight from
// the frame ring through `pentox chip --print`, so no ring parsing here.

Rectangle {
    id: root

    // ~/.local/state/pentox/chip.state, refreshed once a second
    property string stateFile: {
        const state = Qt.env.get("XDG_STATE_HOME", "")
            || (Qt.env.get("HOME", "") + "/.local/state")
        return "file://" + state + "/pentox/chip.state"
    }
    property int refreshMs: 1000

    readonly property bool on: fileReader.contents.indexOf("state=on") >= 0
    readonly property string game: {
        const m = fileReader.contents.match(/^game=(.*)$/m)
        return m ? m[1].trim() : ""
    }
    readonly property string fps: on ? "0 fps" : ""

    visible: on
    implicitWidth: row.implicitWidth + 24
    implicitHeight: 24
    radius: height / 2
    color: "#E60B0812"                      // end4 glass, lavender border
    border.color: "#29B9A3FF"
    border.width: 1

    RowLayout {
        id: row
        anchors.centerIn: parent
        spacing: 6

        Text {
            text: "▲"
            color: "#B9A3FF"
            font.family: "JetBrainsMono Nerd Font"
            font.pixelSize: 12
        }
        Text {
            text: root.game || "game"
            color: "#EDE8FF"
            font.family: "JetBrainsMono Nerd Font"
            font.pixelSize: 11
            elide: Text.ElideRight
            Layout.maximumWidth: 160
        }
        Text {
            text: root.fps
            visible: root.fps !== ""
            color: "#9C8CD4"
            font.family: "JetBrainsMono Nerd Font"
            font.pixelSize: 11
        }
    }

    Timer {
        interval: root.refreshMs
        running: root.visible
        repeat: true
        triggeredOnStart: true
        onTriggered: {
            const out = Quickshell.execProcess("pentox", ["chip", "--print"])
            if (out && out.indexOf("fps") >= 0) {
                const m = out.match(/(\d+)\s*fps/)
                if (m) root.fps = m[1] + " fps"
            }
        }
    }

    FileView {
        id: fileReader
        path: root.stateFile
        blockLoading: false
        watchChanges: true
    }
}
