# Solar Ops Agent

A natural-language agent for managing inverter operations and configuration in residential photovoltaic (PV) systems.

## Goal

**Solar Ops Agent** helps homeowners and installers manage, configure, and troubleshoot their solar inverters through conversational interfaces. Instead of navigating technical menus or manufacturer-specific tools, users describe what they want in plain language.

The agent enables:

- **Set configurations** — Use natural language to set parameters, schedules, and preferences across your inverter(s).
- **Analyze configurations** — Inspect and understand current settings across inverters and the full PV system.
- **Detect problems** — Identify anomalies, faults, and operational issues in the inverter and the whole photovoltaic installation.
- **Create automations** — Build rules and workflows that react to system state, time, or external events.
- **System monitoring** — Track performance, production, and health of the PV system over time.

## Architecture

The application is built around an **inverter-agnostic main module**:

- A core layer defines a common abstraction for inverter operations, configurations, diagnostics, and monitoring.
- **Integrations** implement vendor-specific protocols, APIs, and device support for individual inverter brands and models.
- New inverters can be added through integrations without changing the core logic.

This design supports:

- Multiple inverter types in a single installation
- Future expansion to more manufacturers and models
- Consistent behavior and semantics across different hardware

## Documentation

- **[Growatt MOD 12KTL3-HU Agent Knowledge Base](docs/growatt-mod-12ktl3-hu-agent-kb.md)** — Hardware specs, Modbus TCP integration, register mappings, safety constraints, and operational rules for agent-driven automation of the Growatt MOD 12KTL3-HU hybrid inverter (ShineWiFi-X).


## Roadmap

- [ ] Inverter-agnostic core module
- [ ] First inverter integration(s)
- [ ] Natural-language agent (config, analysis, diagnostics)
- [ ] Automations and system monitoring
- [ ] Additional inverter integrations

---

*Solar Ops Agent is part of the mechanical-joe project.*
