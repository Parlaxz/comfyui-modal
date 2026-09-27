# TEST 1 — freeze scope (308 usable witness runs, no new runs)

## Witness tick health (median inter-tick gap, ms)

| witness | median of medians | p90 | max |
|---|---:|---:|---:|
| reader_py | 10.73 | 10.81 | 10.92 |
| reader_nc | 10.00 | 10.00 | 10.00 |
| control_py | 10.73 | 10.81 | 10.93 |
| control_nc | 10.00 | 10.00 | 10.00 |
| parent_py | 10.74 | 10.83 | 10.91 |

## Pathological reads (>= 250 ms): 102 across 24 runs

| run | provider/region | worker | preadv dur | reader Py gap | reader native gap | other reader Py gaps (max) | control Py gap | control native gap | parent gap |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| im-01-invalid20.json | unspecified:eu-north | 3 | 8744.6 | 11.3 | 10.0 | 12.2 | 11.7 | 10.7 | 11.2 |
| im-01-invalid12.json | gcp:us-east | 2 | 5274.8 | 12.5 | 10.0 | 12.5 | 11.7 | 10.0 | 11.3 |
| im-01-invalid12.json | gcp:us-east | 2 | 5174.1 | 11.2 | 10.0 | 0.0 | 11.2 | 10.0 | 11.1 |
| im-01-invalid6.json | unspecified:eu-north | 3 | 4808.8 | 11.5 | 10.0 | 11.2 | 11.0 | 10.0 | 11.1 |
| im-05-invalid12.json | unspecified:eu-north | 3 | 4510.0 | 11.8 | 10.0 | 11.1 | 11.8 | 10.0 | 11.1 |
| im-01-invalid20.json | unspecified:eu-north | 2 | 4045.8 | 11.2 | 10.0 | 11.1 | 11.1 | 10.0 | 11.1 |
| im-01-invalid6.json | unspecified:eu-north | 2 | 3812.5 | 11.1 | 10.0 | 11.5 | 11.0 | 10.0 | 11.1 |
| im-01-invalid20.json | unspecified:eu-north | 1 | 3621.7 | 11.1 | 10.0 | 12.2 | 11.0 | 10.7 | 11.2 |
| im-01-invalid20.json | unspecified:eu-north | 0 | 2992.5 | 11.3 | 10.0 | 11.3 | 11.7 | 10.0 | 11.1 |
| im-05-invalid12.json | unspecified:eu-north | 2 | 2823.4 | 11.0 | 10.0 | 11.8 | 11.8 | 10.0 | 11.1 |
| im-02-invalid29.json | unspecified:eu-north | 0 | 2374.3 | 11.0 | 10.1 | 11.3 | 11.0 | 10.0 | 11.1 |
| im-02-invalid29.json | unspecified:eu-north | 2 | 2305.6 | 11.1 | 10.0 | 11.6 | 11.1 | 10.0 | 11.1 |
| im-02-invalid29.json | unspecified:eu-north | 1 | 2279.8 | 11.1 | 10.0 | 11.3 | 11.0 | 10.0 | 11.1 |
| im-05-invalid12.json | unspecified:eu-north | 2 | 2156.5 | 11.1 | 10.0 | 11.1 | 11.1 | 10.0 | 11.1 |
| im-01-invalid6.json | unspecified:eu-north | 0 | 2067.3 | 11.1 | 10.0 | 11.1 | 11.0 | 10.0 | 11.1 |
| im-01-invalid6.json | unspecified:eu-north | 0 | 2014.9 | 10.9 | 10.0 | 11.0 | 10.9 | 10.0 | 10.9 |
| im-05-invalid12.json | unspecified:eu-north | 1 | 1798.5 | 11.1 | 10.1 | 11.8 | 11.1 | 10.0 | 11.1 |
| im-01-invalid20.json | unspecified:eu-north | 2 | 1712.1 | 11.3 | 10.0 | 11.3 | 11.7 | 10.0 | 11.1 |
| im-05-invalid12.json | unspecified:eu-north | 0 | 1511.6 | 10.9 | 10.0 | 11.0 | 10.8 | 10.0 | 10.8 |
| im-01-invalid20.json | unspecified:eu-north | 1 | 1500.6 | 11.3 | 10.0 | 11.3 | 11.7 | 10.0 | 11.1 |
| im-01-invalid6.json | unspecified:eu-north | 1 | 1499.0 | 11.0 | 10.0 | 11.0 | 10.9 | 10.0 | 10.9 |
| im-05-invalid12.json | unspecified:eu-north | 1 | 1498.9 | 10.8 | 10.0 | 10.9 | 10.8 | 10.0 | 10.9 |
| im-01-invalid20.json | unspecified:eu-north | 1 | 1413.0 | 11.0 | 10.0 | 11.2 | 11.1 | 10.0 | 11.1 |
| im-01-invalid6.json | unspecified:eu-north | 1 | 1381.0 | 10.9 | 10.0 | 10.9 | 10.9 | 10.0 | 10.9 |
| im-01-invalid6.json | unspecified:eu-north | 0 | 1365.4 | 11.0 | 10.0 | 11.5 | 11.0 | 10.0 | 11.0 |
| im-01-invalid20.json | unspecified:eu-north | 0 | 1353.9 | 10.9 | 10.0 | 11.0 | 10.9 | 10.0 | 11.0 |
| im-02-invalid29.json | unspecified:eu-north | 3 | 1295.1 | 11.6 | 10.0 | 11.5 | 11.1 | 10.0 | 11.1 |
| im-05-invalid12.json | unspecified:eu-north | 0 | 1255.7 | 10.9 | 10.0 | 11.8 | 11.1 | 10.0 | 11.1 |
| im-02-invalid29.json | unspecified:eu-north | 2 | 1184.2 | 11.0 | 10.0 | 11.4 | 11.5 | 10.0 | 11.1 |
| im-01-invalid6.json | unspecified:eu-north | 3 | 1179.9 | 10.9 | 10.0 | 11.1 | 10.9 | 10.0 | 10.9 |
| im-01-invalid20.json | unspecified:eu-north | 2 | 1168.6 | 12.2 | 10.0 | 11.1 | 11.0 | 10.7 | 11.2 |
| im-01-invalid6.json | unspecified:eu-north | 1 | 1127.2 | 11.1 | 10.0 | 11.2 | 11.0 | 10.0 | 11.1 |
| im-02-invalid29.json | unspecified:eu-north | 1 | 1117.0 | 11.1 | 10.0 | 11.0 | 11.0 | 10.0 | 11.0 |
| im-02-invalid29.json | unspecified:eu-north | 2 | 1112.4 | 11.0 | 10.0 | 11.1 | 11.0 | 10.0 | 11.0 |
| im-02-invalid29.json | unspecified:eu-north | 0 | 1086.9 | 11.0 | 10.0 | 11.1 | 11.0 | 10.0 | 11.0 |
| im-02-invalid29.json | unspecified:eu-north | 1 | 1049.1 | 11.0 | 10.0 | 11.0 | 11.0 | 10.0 | 11.0 |
| im-02-invalid29.json | unspecified:eu-north | 0 | 1048.1 | 11.0 | 10.0 | 11.4 | 11.5 | 10.0 | 11.0 |
| im-02-invalid29.json | unspecified:eu-north | 3 | 1046.5 | 11.0 | 10.0 | 11.1 | 11.0 | 10.0 | 11.0 |
| im-01-invalid20.json | unspecified:eu-north | 0 | 1045.2 | 10.9 | 10.0 | 10.9 | 10.9 | 10.0 | 10.9 |
| im-01-invalid6.json | unspecified:eu-north | 2 | 951.4 | 11.1 | 10.0 | 11.1 | 10.9 | 10.0 | 10.9 |
| im-02-invalid29.json | unspecified:eu-north | 3 | 931.2 | 11.3 | 10.0 | 11.4 | 11.5 | 10.0 | 11.1 |
| im-02-invalid29.json | unspecified:eu-north | 3 | 904.8 | 11.0 | 10.0 | 11.0 | 11.0 | 10.0 | 11.0 |
| im-04-invalid22.json | gcp:us-east | 3 | 865.4 | 17.7 | 10.0 | 19.9 | 17.1 | 10.0 | 24.9 |
| im-05-invalid5.json | gcp:us-east | 3 | 845.4 | 24.6 | 10.7 | 24.7 | 27.9 | 10.9 | 19.2 |
| im-08-invalid7.json | gcp:us-east | 3 | 843.3 | 11.4 | 10.0 | 12.3 | 11.1 | 10.0 | 11.2 |
| im-02-invalid29.json | unspecified:eu-north | 3 | 828.8 | 10.9 | 10.0 | 11.0 | 10.9 | 10.0 | 11.0 |
| im-01-invalid12.json | gcp:us-east | 3 | 794.8 | 11.2 | 10.0 | 14.2 | 11.5 | 10.0 | 11.5 |
| im-01-invalid6.json | unspecified:eu-north | 2 | 740.6 | 11.0 | 10.0 | 11.2 | 11.0 | 10.0 | 11.1 |
| im-05-invalid22.json | gcp:us-east | 3 | 736.7 | 12.2 | 10.0 | 13.0 | 11.1 | 10.0 | 11.3 |
| im-05-invalid5.json | gcp:us-east | 1 | 720.7 | 24.6 | 10.0 | 24.7 | 27.9 | 10.9 | 19.2 |
| im-01-invalid20.json | unspecified:eu-north | 0 | 715.0 | 11.0 | 10.0 | 10.9 | 10.9 | 10.0 | 10.9 |
| im-01-invalid6.json | unspecified:eu-north | 1 | 655.7 | 10.8 | 10.0 | 10.8 | 10.8 | 10.0 | 10.8 |
| im-05-invalid12.json | unspecified:eu-north | 1 | 639.3 | 11.1 | 10.0 | 11.1 | 11.8 | 10.0 | 11.1 |
| im-05-invalid23.json | gcp:us-east | 3 | 630.6 | 14.6 | 10.0 | 18.1 | 18.0 | 10.0 | 20.6 |
| im-01-invalid12.json | gcp:us-east | 2 | 617.3 | 11.4 | 10.0 | 14.2 | 11.5 | 10.0 | 11.5 |
| im-04-invalid22.json | gcp:us-east | 2 | 614.8 | 15.4 | 10.8 | 16.6 | 16.5 | 10.0 | 20.6 |
| im-01-invalid20.json | unspecified:eu-north | 0 | 578.8 | 11.0 | 10.0 | 12.2 | 11.0 | 10.7 | 11.2 |
| im-02-invalid29.json | unspecified:eu-north | 2 | 572.7 | 11.1 | 10.0 | 11.0 | 11.0 | 10.0 | 11.0 |
| im-01-invalid6.json | unspecified:eu-north | 1 | 567.5 | 10.9 | 10.0 | 10.9 | 10.9 | 10.0 | 10.9 |
| im-06-invalid22.json | gcp:us-east4 | 3 | 565.4 | 11.8 | 10.0 | 14.6 | 11.2 | 10.0 | 11.1 |
| … 42 more rows in the CSV | | | | | | | | | |

## Enter / gap / exit detail (top 20 by duration)

| run | worker | enter (rel ms) | reader Py gap start (rel ms) | gap end (rel ms) | exit (rel ms) |
|---|---:|---:|---:|---:|---:|
| im-01-invalid20.json | 3 | 0.0 | 5285.2 | 5296.5 | 8744.6 |
| im-01-invalid12.json | 2 | 0.0 | 1423.8 | 1436.3 | 5274.8 |
| im-01-invalid12.json | 2 | 0.0 | 3793.7 | 3804.9 | 5174.1 |
| im-01-invalid6.json | 3 | 0.0 | 2179.1 | 2190.6 | 4808.8 |
| im-05-invalid12.json | 3 | 0.0 | 2226.3 | 2238.1 | 4510.0 |
| im-01-invalid20.json | 2 | 0.0 | 3276.1 | 3287.2 | 4045.8 |
| im-01-invalid6.json | 2 | 0.0 | 2132.0 | 2143.1 | 3812.5 |
| im-01-invalid20.json | 1 | 0.0 | 321.8 | 332.8 | 3621.7 |
| im-01-invalid20.json | 0 | 0.0 | 2279.0 | 2290.3 | 2992.5 |
| im-05-invalid12.json | 2 | 0.0 | 2747.5 | 2758.5 | 2823.4 |
| im-02-invalid29.json | 0 | 0.0 | 1759.0 | 1770.0 | 2374.3 |
| im-02-invalid29.json | 2 | 0.0 | 1501.6 | 1512.7 | 2305.6 |
| im-02-invalid29.json | 1 | 0.0 | 1855.2 | 1866.3 | 2279.8 |
| im-05-invalid12.json | 2 | 0.0 | 2135.9 | 2147.0 | 2156.5 |
| im-01-invalid6.json | 0 | 0.0 | 1067.8 | 1078.9 | 2067.3 |
| im-01-invalid6.json | 0 | 0.0 | 1838.3 | 1849.2 | 2014.9 |
| im-05-invalid12.json | 1 | 0.0 | 180.6 | 191.7 | 1798.5 |
| im-01-invalid20.json | 2 | 0.0 | 1042.4 | 1053.7 | 1712.1 |
| im-05-invalid12.json | 0 | 0.0 | 73.2 | 84.1 | 1511.6 |
| im-01-invalid20.json | 1 | 0.0 | 776.8 | 788.0 | 1500.6 |

## Gap magnitudes vs baseline

- reader Py (own)            median=11.2 ms  p90=19.2  max=79.9 ms
- reader native (own)        median=10.0 ms  p90=10.2  max=19.1 ms
- other readers Py (max)     median=11.5 ms  p90=23.4  max=78.7 ms
- control Py                 median=11.1 ms  p90=17.9  max=63.2 ms
- control native             median=10.0 ms  p90=10.7  max=22.3 ms
- parent Py                  median=11.1 ms  p90=19.2  max=69.0 ms

## Classification of the 5 witnesses, per sick read

| class | meaning | count | share |
|---|---|---:|---:|
| E_neither_froze | no witness froze (gap elsewhere) | 102 | 100% |

