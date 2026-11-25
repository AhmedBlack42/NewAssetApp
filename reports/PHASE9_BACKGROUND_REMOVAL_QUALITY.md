# Phase 9 Background-Removal Quality

## Sample and method

Four representative crops were processed with the existing bundled BiRefNet model on CPU. The sources cover a busy indoor scene, bright background with overlapping people, low-resolution lying pose, and dim cluttered room. Source hashes, crop ROIs, output sizes, alpha coverage, and timing are recorded in `gui_screenshots/phase9/birefnet/quality_manifest.json`.

The actual RGBA WebP files and checkerboard composites are in `gui_screenshots/phase9/birefnet/`. Visual review was made from reduced-size inspection copies of the composites; those copies preserve the rendered evidence while making the images viewable in this session.

## Visual findings

| Sample | Visual assessment |
|---|---|
| Busy multi-person room | Main foreground subject is mostly retained with a clear transparent background. Fine fabric edges are usable. The ROI itself ends at the right image boundary, so the arm is cut by the selected crop; that is crop geometry, not a mask defect. |
| Bright overlapping subjects | Main foreground subject is retained. Hair edges show some softness/halo and the overlapping background/subject boundary needs manual inspection. |
| Low-resolution lying pose | Main subject is separated. Fine net/fabric and shoe edges are soft, with a faint dark fringe in places; resolution limits detail. |
| Dim cluttered room | Main subject and skirt are retained with a largely clean background. Some fine hair/finger edges are softened. |

Across these four outputs, no broad opaque background remnant is apparent in the checkerboard composites. The model retains the main foreground in each case. Hair, low-resolution mesh/fabric, and some fine contours have softness or small edge halos. The composites are evidence of these four examples only, not a general accuracy guarantee.

## Processing times

The four crops took 114.10, 120.58, 127.81, and 126.91 seconds respectively (mean **122.35 seconds**). The transparent WebPs preserve the source crop dimensions and RGBA output.

## Suitability

Mask quality is **conditionally usable for human-reviewed normal export** on these examples, with manual inspection required for fine edges and crop boundaries. The approximately two-minute CPU time per crop is not acceptable for efficient batch throughput. Background removal remains optional; if disabled or it fails, the app retains the original crop and reports the fallback. These results do not constitute user acceptance or a live GUI export test.
