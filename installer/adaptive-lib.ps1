function Resolve-AdaptivePackage([string]$PackageRoot, [string]$Target, [string]$Action='Install') {
    $script:PatchPhase='本机原图结构检查与自动适配'
    $rootManifest=Read-PatchManifest $PackageRoot
    $adapter=Join-Path $PackageRoot $rootManifest.adaptive.executable
    Assert-Digest $adapter $rootManifest.adaptive.sha256 'Package'
    Write-Host '正在读取本机原图并检查训练接口；此阶段不会修改地图……'
    $resultPath=Join-Path ([IO.Path]::GetTempPath()) ('5ehub-adapt-'+[Guid]::NewGuid().ToString('N')+'.json')
    try {
        $adapterArgs=@('--package',$PackageRoot,'--target',$Target,'--action',$Action,'--result',$resultPath)
        if($env:FIVEHUB_ADAPT_CACHE){$adapterArgs+=@('--cache-root',$env:FIVEHUB_ADAPT_CACHE)}
        & $adapter @adapterArgs | Out-Null
        $adapterExit=$LASTEXITCODE
        if (-not (Test-Path -LiteralPath $resultPath -PathType Leaf)) {
            Throw-PatchIssue 'ADAPTER_START_FAILED' '自动适配程序未生成结果。' @('退出代码：'+$adapterExit) '重新完整解压补丁，检查安全软件是否拦截 adapter/5EHubAdapter.exe。'
        }
        $result=Get-Content -LiteralPath $resultPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($adapterExit -ne 0 -or -not $result.ok) {
            Throw-PatchIssue $result.code $result.message @('地图：'+$Target) '原图结构变化时请保留完整输出；文件不完整时先等待 Steam 下载完成。不要修改校验值。'
        }
        Write-Host ('兼容性检查通过：'+$result.sourceEntries+' 个原图资源；验证输出 '+$result.verifiedEntries+' 个资源。') -ForegroundColor Green
        Write-Host '已生成与本机原图匹配的补丁。'
        return $result
    }
    finally { if(Test-Path -LiteralPath $resultPath){Remove-Item -LiteralPath $resultPath -Force} }
}
