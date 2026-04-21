param(
  [string]$HostUrl = "http://127.0.0.1:8080",
  [int]$Users = 80,
  [int]$SpawnRate = 10,
  [string]$RunTime = "5m",
  [string]$CsvPrefix = "results/raw/locust_run"
)

locust `
  -f loadtest/locust/locustfile.py `
  --host $HostUrl `
  --headless `
  --users $Users `
  --spawn-rate $SpawnRate `
  --run-time $RunTime `
  --csv $CsvPrefix `
  --only-summary

