# Phase 9 BiRefNet Performance

## Findings

BiRefNet is loaded once into a process-level runtime guarded by a lock, then reused for subsequent crops. The bundled model weights were not changed. A bounded, thread-safe in-memory alpha-mask LRU cache (32 MiB) is keyed by model/source/crop identity when a stable key is available.

The existing path resizes each crop to 1024×1024, converts and normalizes it, runs one CPU inference, and resizes the resulting mask to crop dimensions. In the representative run, preprocessing and postprocessing took only about 0.02–0.09 seconds each; inference dominated. The model load itself took about 3.99 seconds (excluding imports). There is no batching in this current crop path; each crop is inferred separately.

## Measurement (CPU, 4 torch threads)

| Sample | Crop size | Inference | Total segment time |
|---|---:|---:|---:|
| Busy multi-person room | 720×1345 | 113.99 s | 114.10 s |
| Bright overlapping subjects | 610×518 | 120.50 s | 120.58 s |
| Low-resolution lying pose | 460×345 | 127.73 s | 127.81 s |
| Dim cluttered room | 730×1000 | 126.79 s | 126.91 s |

Mean observed segment time: **122.35 seconds per crop**. Import/model initialization is a separate first-run cost. The near-fixed, very high inference time across crop dimensions indicates the 1024-square CPU model inference is the bottleneck, not image conversion or repeated model loading.

## Resilience and control

- Fullbody background removal is configurable in the normal workflow; disabling it retains the original crop and records the choice.
- If removal raises an error, the original crop is exported and the fallback reason is surfaced in the result/history.
- Progress is reported per item by the worker.
- Cancellation is cooperative between crops. It does not interrupt an in-flight model inference; completed exports remain in place and unprocessed crop IDs are reported.
- Cache tests verify reuse for the same source/crop identity and eviction at the byte limit.

## Assessment

Runtime reuse and caching remove avoidable setup/repeated work, but they do not solve the CPU inference bottleneck. Current CPU background removal is functionally wired but too slow for normal multi-crop throughput. No alternative model, dependency, or weight change is proposed or made. Consider an explicitly approved performance experiment on inference resolution/thread settings only after verifying mask quality against this baseline.
