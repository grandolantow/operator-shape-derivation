param(
    [Parameter(Mandatory = $true)][string]$TaskDir,
    [Parameter(Mandatory = $true)][Alias("RepoRoot")][string]$CannbotRoot,
    [string]$WorkflowSkill,
    [switch]$Apply
)

$installer = Join-Path $PSScriptRoot 'install_codex.py'
$arguments = @('-B', $installer, '--task-dir', $TaskDir)
if ($CannbotRoot) { $arguments += @('--cannbot-root', $CannbotRoot) }
if ($WorkflowSkill) { $arguments += @('--workflow-skill', $WorkflowSkill) }
if ($Apply) { $arguments += '--apply' }

& python @arguments
exit $LASTEXITCODE
