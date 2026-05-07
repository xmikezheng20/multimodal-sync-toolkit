# Analysis Scripts

Script entry points for validation and timing conversion will live here.

These scripts should call reusable code from `src/multimodal_sync/`.

Validate one recorded session:

```bash
python scripts/validate_session.py \
  -s /path/to/session \
  -c configs/example_session_01_50hz.yaml \
  --log-file /path/to/session/logs/validate_session.log
```
