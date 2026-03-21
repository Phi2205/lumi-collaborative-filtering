# PowerShell script to register an hourly task for Lumi Feature Refresh

$taskName = "Lumi_Feature_Refresh_Hourly"
$pythonPath = "C:\Users\Administrator\AppData\Local\Programs\Python\Python313\python.exe"
$scriptPath = "app/jobs/refresh_features.py"
$workingDir = "c:\lumi\lumi-collaborative-filtering"

# Define the action
$action = New-ScheduledTaskAction -Execute $pythonPath -Argument $scriptPath -WorkingDirectory $workingDir

# Define the trigger (Run every day, repeat every 1 hour)
$trigger = New-ScheduledTaskTrigger -Daily -At (Get-Date).ToString("HH:mm")
$trigger.Repetition = (New-ScheduledTaskRepetitionPattern -Interval (New-TimeSpan -Hours 1) -Duration ([TimeSpan]::MaxValue))

# Define the principal (User context)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType InteractiveOrPassword

# Register the task
Register-ScheduledTask -Action $action -Trigger $trigger -Principal $principal -TaskName $taskName -Force

Write-Host "✅ Task '$taskName' has been registered successfully."
Write-Host "🕒 It will run every 1 hour starting from now."
