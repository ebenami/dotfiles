# Ghostty and Terminator

Ghostty retains the existing shared settings, including every keyboard binding.
Its loader reads the linked `shared` and platform files. macOS uses Monaco;
Ubuntu uses the system monospace font.

Terminator settings are copied and merged into
`${XDG_CONFIG_HOME:-~/.config}/terminator/config` on Ubuntu. Only selected keys in
`[profiles] / [[default]]` are owned by this repository. Existing `[keybindings]`,
`[layouts]`, other profiles, plugins, and custom commands remain untouched during
apply and are excluded from capture. Tabs using another profile retain that
profile; select `default` in Terminator to use these settings.

| Setting | Terminator mapping |
| --- | --- |
| Background / foreground | Black / `#bbbbbb` |
| ANSI colors | Same 16-color palette as Ghostty |
| Font | `Monospace 12`, matching the Ubuntu Ghostty override as closely as rendering allows |
| Cursor | Nonblinking block with `#bbbbbb` background and white text |
| Background opacity | Solid |
| Selection copying | Copy selected text to the clipboard |
| Scrollback | Infinite, approximating Ghostty's very large byte limit |
| Bell | Audible, urgency, and titlebar indication |
| Keyboard shortcuts | Existing local bindings preserved; no managed binding section |

Ghostty's custom selection colors, separate bold color, exact padding, initial
80-by-25 character geometry, mouse-reporting controls, and arbitrary key-to-escape
sequences do not all have equivalent supported Terminator profile options. They
are left to the terminal/desktop rather than simulated through unrelated settings.
The two scrollback limits use different units/semantics and are not identical.

Terminator uses ConfigObj's nested sections, not flat INI. The sync engine parses
and merges that native format, preserving other sections. Close Terminator before
applying so its preferences writer does not overwrite the change; then reopen it.
The terminal application itself is not installed or changed by config-only setup.

References: [Terminator configuration](https://github.com/gnome-terminator/terminator/blob/master/doc/terminator_config.adoc),
[upstream supported defaults](https://github.com/gnome-terminator/terminator/blob/master/terminatorlib/config.py).
