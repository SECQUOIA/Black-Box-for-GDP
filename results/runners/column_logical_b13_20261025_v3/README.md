# Column 64/B13 Dantzig package v3

Version 3 corrects the classification of unrestricted wdavdaemon system activity while keeping all CPU load limits and compute-task checks.
The service is assessed by the unchanged 5% interval and 2% full-window limits, and its activity remains in the raw records and launch log.
The server occupancy and runtime will be checked afresh when the user launches v3.
The experiment plan and 624 experiment input, baseline, optimizer and analysis files are byte-identical to v2.
All 95 related tests pass, including regression fixtures for the reported service activity and continued rejection of actual compute occupation.
The original 3,430-job input audit passes without modification.
Both earlier packages and their blocked run directories remain preserved, and v3 starts in a fresh result directory.
No formal search job, original process NLP computation, commit or push was performed during preparation.
Upload, launch, tail, resume and result-download commands are in COMMANDS.md.
