## CNC tool bridge examples

Send these as the `content` of the Open Interpreter tool request (e.g., via the JL Engine "Run Tool (OI)" button when Tools are ON).

### Status
```json
{"mode": "tool", "tool": "cnc", "payload": {"action": "status"}}
```

### Spindle on / off
```json
{"mode": "tool", "tool": "cnc", "payload": {"action": "spindle_on", "speed": 500}}
{"mode": "tool", "tool": "cnc", "payload": {"action": "spindle_off"}}
```

### Jog (relative, clamped to +/-50mm and feed <= 1000)
```json
{"mode": "tool", "tool": "cnc", "payload": {"action": "jog", "dx": 1.0, "dy": 0.0, "dz": 0.0, "feed": 200.0}}
{"mode": "tool", "tool": "cnc", "payload": {"action": "jog", "dx": 0.0, "dy": -1.0, "dz": 0.0, "feed": 300.0}}
{"mode": "tool", "tool": "cnc", "payload": {"action": "jog", "dx": 0.0, "dy": 0.0, "dz": -0.5, "feed": 150.0}}
```
