# Tests

Pure logic only: the parts that decide what gets written to a remote, and the protocol framing
that a real press would otherwise be the only way to exercise. Nothing here needs Home
Assistant, bluezero, a broker or a radio — the modules are loaded straight from their files by
`conftest.py`, so the suite runs anywhere Python does.

```bash
python3 -m venv .venv-test && .venv-test/bin/pip install pytest
.venv-test/bin/python -m pytest tests/ -q
```

| File | Covers |
| --- | --- |
| `test_addressing.py` | how many native tiles a setup can hold, and which address each one gets |
| `test_targets.py` | which bridge a tile is bound to, and with which key |
| `test_bridge_transport.py` | advertisement layout, ACL fragmentation, L2CAP reassembly, the HCI event mask |

Two real defects were found by writing these: an address written with dashes was treated as a
different bridge, and a hand-picked address did not count against its controller's capacity.
