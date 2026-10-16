// Extend the map's own local save slot. Do not store transient spray/camera state.
const __codexPreferenceKey="codexRecoilPreferences";
const __codexPreferenceSession=Date.now().toString(36)+"-"+Math.random().toString(36).slice(2);
let __codexPreferencesReady=false,__codexPreferencesLast="",__codexPreferenceCheckMs=0;
function __codexReadSave(){
    try{
        const data=JSON.parse(Instance.GetSaveData()||"{}");
        return data&&typeof data==="object"&&!Array.isArray(data)?data:{};
    }catch(e){return {};}
}
function __codexCapturePreferences(){
    return {
        schema:1,guide:__5ehubRmGuideEnabled,autoAim:__5ehubAuto,target:__5ehubRmPart,
        screenShake:__5ehubScreenShake,botInvincible:__5ehubBotInvincible,drawingVersion:__5ehubDrawingVersion(),
        guideWhen:__5ehubGuideWhen,viewport:{...__5ehubViewport},bulletTime:__codexBulletTimeScale,
        peek:{mode:peekMode.peekMode,speed:peekMode.iBotMoveSpeed,
            heightLow:peekMode.iBotSpawnHeightLow,heightHigh:peekMode.iBotSpawnHeightHigh,
            heightSign:peekMode.bBotSpawnHeightSign,direction:peekMode.nBotSpawnDirection,
            directionButtons:peekMode.nBotSpawnDirectionTypeStatus.slice(1,3)}
    };
}
function __codexPreferenceSignature(){
    return JSON.stringify({extension:__codexCapturePreferences(),native:Settings.serialize()});
}
function __codexRestorePreferences(data){
    if(!data||data.schema!==1)return;
    if(typeof data.guide==="boolean")__5ehubRmGuideEnabled=data.guide;
    if(typeof data.autoAim==="boolean")__5ehubAuto=data.autoAim;
    if(["head","neck","chest"].includes(data.target))__5ehubRmPart=data.target;
    if(typeof data.screenShake==="boolean")__5ehubSetScreenShake(data.screenShake);
    if(typeof data.botInvincible==="boolean")__5ehubSetBotInvincible(data.botInvincible);
    if(data.drawingVersion===1||data.drawingVersion===2)__5ehubSetDrawingVersion(data.drawingVersion);
    if(["always","fire","visible"].includes(data.guideWhen))__5ehubSetGuideWhen(data.guideWhen);
    if(data.viewport&&Number.isInteger(data.viewport.width)&&Number.isInteger(data.viewport.height))
        __5ehubSetViewport(data.viewport.width,data.viewport.height);
    if(typeof data.bulletTime==="number"&&Number.isFinite(data.bulletTime))__codexSetBulletTime(data.bulletTime);
    const p=data.peek;
    if(p&&typeof p==="object"){
        if(p.mode===PeekModeType.static||p.mode===PeekModeType.dynamic)peekMode.peekMode=p.mode;
        if(Number.isFinite(p.speed)&&p.speed>=0&&p.speed<=10000)peekMode.iBotMoveSpeed=p.speed;
        if(Number.isFinite(p.heightLow)&&Number.isFinite(p.heightHigh)&&p.heightLow>=peekMode.iBotSpawnHeightMin&&p.heightHigh<=peekMode.iBotSpawnHeightMax&&p.heightLow<=p.heightHigh){
            peekMode.iBotSpawnHeightLow=p.heightLow;peekMode.iBotSpawnHeightHigh=p.heightHigh;
        }
        if(typeof p.heightSign==="boolean")peekMode.bBotSpawnHeightSign=p.heightSign;
        if([0,1,3,4].includes(p.direction)){
            peekMode.nBotSpawnDirection=p.direction;
            peekMode.nBotSpawnDirectionTypeStatus=[undefined,p.direction===1||p.direction===4,p.direction===3||p.direction===4];
        }
        peekMode.peekBotSpawnHeightDisplay();
        EntFire("peek_btn_mode_*","Alpha","0");
        EntFire("peek_btn_mode_"+(peekMode.peekMode===PeekModeType.static?"static":"dynamic"),"Alpha","255");
        EntFire("peek_worldtext_botMoveSpeed_number","SetMessage",peekMode.peekMode===PeekModeType.static?"0":String(peekMode.iBotMoveSpeed));
        EntFire("peek_trigger_push_*","SetPushSpeed",String(peekMode.iBotMoveSpeed));
        EntFire("peek_prop_marker_l","skin",peekMode.nBotSpawnDirectionTypeStatus[1]?"1":"0");
        EntFire("peek_prop_marker_r","skin",peekMode.nBotSpawnDirectionTypeStatus[2]?"1":"0");
    }
    // Emit an authoritative state even when restoring the same boolean value.
    __5ehubPublishShakeState();
}
const __codexOriginalSaveData=saveData;
saveData=function(...args){
    // A startup timer must not overwrite the previous extension before loadData.
    const previous=__codexReadSave()[__codexPreferenceKey];
    const result=__codexOriginalSaveData(...args),data=__codexReadSave();
    const preferences=__codexPreferencesReady?__codexCapturePreferences():previous;
    if(preferences!==undefined)data[__codexPreferenceKey]=preferences;
    Instance.SetSaveData(JSON.stringify(data));
    if(__codexPreferencesReady)__codexPreferencesLast=__codexPreferenceSignature();
    return result;
};
const __codexOriginalLoadData=loadData;
loadData=async function(...args){
    const saved=__codexReadSave()[__codexPreferenceKey];
    await __codexOriginalLoadData(...args);
    __codexRestorePreferences(saved);
    __codexPreferencesReady=true;
    __codexPreferencesLast=__codexPreferenceSignature();
    __5ehubPublishShakeState();
    Instance.Msg("[AK-PREFS] "+(saved?.schema===1?"restored":"defaults"));
};
function __codexPreferencesTick(force=false){
    const now=Date.now();
    if(!__codexPreferencesReady||(!force&&now-__codexPreferenceCheckMs<100))return;
    __codexPreferenceCheckMs=now;
    if(!PlayerMgr.resolveUser())return;
    if(__codexPreferenceSignature()!==__codexPreferencesLast)saveData();
}
// Menu actions save immediately; native wall buttons are caught by Think.
const __codexPreferenceMenuProvider=_menuProvider;
registerMenuProvider(player=>{
    const data=__codexPreferenceMenuProvider(player);
    if(!data?.onSelect)return data;
    return {...data,onSelect:(...args)=>{
        const result=data.onSelect(...args);
        __codexPreferencesTick(true);
        return result;
    }};
});
__5ehubRmConsoleCommand("akprefs",args=>Instance.Msg("[AK-PREFS-STATE] "+JSON.stringify({request:String(args||"").trim().slice(0,64),session:__codexPreferenceSession,ready:__codexPreferencesReady,preferences:__codexCapturePreferences()})));
// Restore a bounded, encoded diagnostic backup through the same validated
// preference restoration used by map startup; native statistics stay intact.
__5ehubRmConsoleCommand("akprefsrestore",args=>{
    try{
        if(args.length>8192)return;
        const data=JSON.parse(decodeURIComponent(args.trim()));
        if(data?.schema!==1)return;
        __codexRestorePreferences(data);__codexPreferencesTick(true);
    }catch(e){Instance.Msg("[AK-PREFS] invalid diagnostic restore");}
});
