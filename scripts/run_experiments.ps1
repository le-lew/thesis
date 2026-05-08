param(
  [string]$ConfigPath = "scripts/experiment.config.json",
  [switch]$SkipPreflight
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-Checked {
  param([string]$Command)
  Write-Host "> $Command"
  Invoke-Expression $Command
}

function Wait-Rollout {
  param(
    [string]$Namespace,
    [string]$Deployment,
    [int]$TimeoutSec
  )
  Invoke-Checked "kubectl -n $Namespace rollout status deployment/$Deployment --timeout=${TimeoutSec}s"
}

function Start-PortForward {
  param(
    [string]$Namespace,
    [string]$Service,
    [int]$LocalPort,
    [int]$ServicePort
  )
  $log = New-TemporaryFile
  $cmd = "kubectl -n $Namespace port-forward svc/$Service ${LocalPort}:${ServicePort}"
  $errLog = New-TemporaryFile
  $proc = Start-Process -FilePath "powershell" -ArgumentList "-NoProfile", "-Command", $cmd -WindowStyle Hidden -PassThru -RedirectStandardOutput $log.FullName -RedirectStandardError $errLog.FullName
  Start-Sleep -Seconds 3
  return @{ Process = $proc; LogPath = $log.FullName; ErrPath = $errLog.FullName }
}

function Stop-IfRunning {
  param($Proc)
  if ($null -ne $Proc -and -not $Proc.HasExited) {
    Stop-Process -Id $Proc.Id -Force
  }
}

function Start-TopSampler {
  param(
    [string]$Namespace,
    [int]$IntervalSec,
    [string]$OutPath
  )
  $script = @"
while (`$true) {
  `$ts = (Get-Date).ToString('o')
  try {
    kubectl -n $Namespace top pods --no-headers | ForEach-Object { "`$ts`t`$_" }
  } catch {
    "`$ts`tTOP_FAILED`t`$(`$_.Exception.Message)"
  }
  Start-Sleep -Seconds $IntervalSec
}
"@
  $tmpDir = Join-Path (Get-Location) ".cache/runtime"
  New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null
  $tmp = Join-Path $tmpDir ("top-sampler-{0}.ps1" -f ([guid]::NewGuid().ToString("N")))
  Set-Content -LiteralPath $tmp -Value $script -Encoding UTF8
  $errLog = New-TemporaryFile
  $proc = Start-Process -FilePath "powershell" -ArgumentList "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", $tmp -WindowStyle Hidden -PassThru -RedirectStandardOutput $OutPath -RedirectStandardError $errLog.FullName
  return @{ Process = $proc; ScriptPath = $tmp; ErrPath = $errLog.FullName }
}

function Apply-Strategy {
  param(
    [string]$Strategy,
    [object]$Cfg
  )
  $ns = $Cfg.environment.k8s_namespace
  $dep = $Cfg.environment.deployment_name

  Invoke-Checked "kubectl -n $ns delete hpa --all --ignore-not-found"
  if ($script:VpaExists) {
    Invoke-Checked "kubectl -n $ns delete vpa --all --ignore-not-found"
  }

  switch ($Strategy) {
    "static" {
      Invoke-Checked "kubectl -n $ns scale deployment/$dep --replicas=2"
    }
    "hpa_cpu" {
      Invoke-Checked "kubectl apply -f deploy/hpa/hpa-cpu.yaml"
    }
    "hpa_multi" {
      Invoke-Checked "kubectl apply -f deploy/hpa/hpa-multi.yaml"
    }
    "hpa_vpa" {
      Invoke-Checked "kubectl apply -f deploy/hpa/hpa-multi.yaml"
      if ($script:VpaExists) {
        Invoke-Checked "kubectl apply -f deploy/vpa/vpa-initial.yaml"
      } else {
        Write-Host "[Warn] VPA CRD not found, skip VPA apply and continue as hpa_multi fallback."
      }
    }
    default {
      throw "Unknown strategy: $Strategy"
    }
  }
}

function Assert-CustomMetricReady {
  param(
    [string]$Namespace,
    [string]$MetricName
  )
  $resources = kubectl get --raw "/apis/custom.metrics.k8s.io/v1beta1" 2>$null
  if ($LASTEXITCODE -ne 0 -or $resources -notmatch $MetricName) {
    throw "Custom metric API is not ready or metric missing: $MetricName"
  }
}

function Assert-VpaReady {
  $vpaApi = kubectl api-resources --verbs=list -o name 2>$null | Select-String -Pattern "verticalpodautoscalers.autoscaling.k8s.io"
  if ($null -eq $vpaApi) {
    throw "VPA CRD not found. Install VPA before running the hpa_vpa strategy."
  }
}

function Write-Manifest {
  param(
    [string]$OutFile,
    [string]$Strategy,
    [int]$RunIndex,
    [object]$Cfg
  )
  $gitCommit = "unknown"
  $k8sVersion = "unknown"
  try {
    $gitCommit = (git rev-parse HEAD).Trim()
  } catch {}
  try {
    $k8sVersion = (kubectl get nodes -o jsonpath="{.items[0].status.nodeInfo.kubeletVersion}" 2>$null).Trim()
  } catch {}

  $manifest = [ordered]@{
    timestamp = (Get-Date).ToString("o")
    strategy = $Strategy
    scenario = $Cfg.experiment.scenario
    run_index = $RunIndex
    config = $Cfg
    environment = [ordered]@{
      kubectl_context = (kubectl config current-context)
      kubernetes_version = $k8sVersion
      git_commit = $gitCommit
    }
  }
  $manifest | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 $OutFile
}

$env:MPLCONFIGDIR = Join-Path (Get-Location) ".cache/matplotlib"
New-Item -ItemType Directory -Path $env:MPLCONFIGDIR -Force | Out-Null

$cfg = Get-Content -Raw -Encoding UTF8 $ConfigPath | ConvertFrom-Json
$ns = $cfg.environment.k8s_namespace
$svc = $cfg.environment.service_name
$svcPort = [int]$cfg.environment.service_port
$localPort = [int]$cfg.environment.local_port
$dep = $cfg.environment.deployment_name
$repeats = [int]$cfg.experiment.repeats
$scenario = $cfg.experiment.scenario
$script:VpaExists = $false
try {
  $vpaApi = kubectl api-resources --verbs=list -o name 2>$null | Select-String -Pattern "verticalpodautoscalers"
  if ($null -ne $vpaApi) {
    $script:VpaExists = $true
  }
} catch {
  $script:VpaExists = $false
}

if (-not $SkipPreflight) {
  Invoke-Checked "kubectl apply -f deploy/base/namespace.yaml"
  Invoke-Checked "kubectl apply -f deploy/base/deployment.yaml"
  Invoke-Checked "kubectl apply -f deploy/base/service.yaml"
  Wait-Rollout -Namespace $ns -Deployment $dep -TimeoutSec ([int]$cfg.experiment.max_wait_rollout_seconds)
  Write-Host "[Preflight] verifying metrics API..."
  Invoke-Checked "kubectl top pods -n $ns"
  if ($cfg.strategies -contains "hpa_multi" -or $cfg.strategies -contains "hpa_vpa") {
    Write-Host "[Preflight] verifying custom metrics API..."
    Assert-CustomMetricReady -Namespace $ns -MetricName $cfg.qps_metric_name
  }
  if ($cfg.strategies -contains "hpa_vpa") {
    Write-Host "[Preflight] verifying VPA API..."
    Assert-VpaReady
    $script:VpaExists = $true
  }
}

foreach ($strategy in $cfg.strategies) {
  for ($i = 1; $i -le $repeats; $i++) {
    $runId = "{0}_{1:yyyyMMdd_HHmmss}_r{2}" -f $strategy, (Get-Date), $i
    $runDir = Join-Path "results/raw" (Join-Path $strategy (Join-Path $scenario $runId))
    New-Item -ItemType Directory -Path $runDir -Force | Out-Null

    Write-Host "=== Strategy=$strategy Run=$i Dir=$runDir ==="

    Apply-Strategy -Strategy $strategy -Cfg $cfg
    Wait-Rollout -Namespace $ns -Deployment $dep -TimeoutSec ([int]$cfg.experiment.max_wait_rollout_seconds)
    Start-Sleep -Seconds ([int]$cfg.experiment.warmup_seconds)

    $pf = Start-PortForward -Namespace $ns -Service $svc -LocalPort $localPort -ServicePort $svcPort
    $topPath = Join-Path $runDir "top_pods.log"
    $topSampler = Start-TopSampler -Namespace $ns -IntervalSec ([int]$cfg.experiment.top_snapshot_interval_seconds) -OutPath $topPath

    try {
      Invoke-Checked "kubectl -n $ns get hpa -o yaml > `"$runDir/hpa.yaml`""
      if ($script:VpaExists) {
        Invoke-Checked "kubectl -n $ns get vpa -o yaml > `"$runDir/vpa.yaml`""
      } else {
        Set-Content -Encoding UTF8 -Path (Join-Path $runDir "vpa.yaml") -Value "# vpa api resource not found on cluster"
      }
      Invoke-Checked "kubectl -n $ns get events --sort-by=.metadata.creationTimestamp > `"$runDir/events_before.txt`""

      $csvPrefix = Join-Path $runDir "locust"
      Invoke-Checked "locust -f loadtest/locust/locustfile.py --host http://127.0.0.1:$localPort --headless --users $($cfg.experiment.users) --spawn-rate $($cfg.experiment.spawn_rate) --run-time $($cfg.experiment.run_time) --csv `"$csvPrefix`" --only-summary"

      Invoke-Checked "kubectl -n $ns get hpa -o wide > `"$runDir/hpa_after.txt`""
      Invoke-Checked "kubectl -n $ns describe hpa > `"$runDir/hpa_describe.txt`""
      Invoke-Checked "kubectl -n $ns get pods -o wide > `"$runDir/pods_after.txt`""
      Invoke-Checked "kubectl -n $ns get events --sort-by=.metadata.creationTimestamp > `"$runDir/events_after.txt`""

      Write-Manifest -OutFile (Join-Path $runDir "manifest.json") -Strategy $strategy -RunIndex $i -Cfg $cfg
    }
    finally {
      Stop-IfRunning -Proc $pf.Process
      Stop-IfRunning -Proc $topSampler.Process
      Remove-Item -LiteralPath $topSampler.ScriptPath -Force -ErrorAction SilentlyContinue
      Start-Sleep -Seconds ([int]$cfg.experiment.cooldown_seconds)
    }
  }
}

Invoke-Checked "python results/aggregate_experiment.py --config `"$ConfigPath`" --raw-root results/raw --out results/processed/experiment_metrics.csv"
Invoke-Checked "python results/plot_results.py --input results/processed/experiment_metrics.csv --outdir results/figures"
Write-Host "All experiments done."
