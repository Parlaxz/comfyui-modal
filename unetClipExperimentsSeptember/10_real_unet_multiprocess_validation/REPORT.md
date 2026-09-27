# Workspace 3 Testing 7 — real UNET validation



The seven requested answers below use only V1 same-file evidence.



1. A: median wall 1.877143 s, mean wall 2.131800 s, fastest wall 1.521959 s; median 6.586236 GB/s, mean 6.218580 GB/s, fastest 8.088174 GB/s. Raw: results_real_unet_validation/raw/real_unet_validation_v1-A1-attempt001.json, results_real_unet_validation/raw/real_unet_validation_v1-A2-attempt001.json, results_real_unet_validation/raw/real_unet_validation_v1-A3-attempt001.json, results_real_unet_validation/raw/real_unet_validation_v1-A4-attempt001.json, results_real_unet_validation/raw/real_unet_validation_v1-A5-attempt001.json, results_real_unet_validation/raw/real_unet_validation_v1-A6-attempt001.json.

2. B: median wall 2.492133 s, mean wall 2.400294 s, fastest wall 1.825540 s; median 4.940542 GB/s, mean 5.205899 GB/s, fastest 6.743137 GB/s. Raw: results_real_unet_validation/raw/real_unet_validation_v1-B1-attempt001.json, results_real_unet_validation/raw/real_unet_validation_v1-B2-attempt001.json, results_real_unet_validation/raw/real_unet_validation_v1-B3-attempt001.json, results_real_unet_validation/raw/real_unet_validation_v1-B4-attempt001.json, results_real_unet_validation/raw/real_unet_validation_v1-B5-attempt001.json, results_real_unet_validation/raw/real_unet_validation_v1-B6-attempt001.json.

3. B median improvement over A: wall saved -0.614990 s (-32.762018%); throughput gain -1.645694 GB/s (-24.986868%).

4. B process startup median: 0.101424 s.

5. No; A is faster than B by median wall time, so multiprocessing does not win.

6. B median wall improvement is -32.762018%: A wins (B is slower).

7. No; do not advance B to a final-RAM/H2D integration test because A wins the real-model read.
