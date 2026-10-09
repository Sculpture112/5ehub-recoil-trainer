// Workshop-local 5EHub AK guide. Runs only in this map's local peek mode.
// Bullet compensation and fixed first-person display calibration are separate.
const __5ehubAkRecoil = __MEASURED__;
const __5ehubWeaponProfiles = __WEAPON_PROFILES__;
const __5ehubWeaponCatalog = __WEAPON_CATALOG__;
const __5ehubDisplayCalibration = __DISPLAY_CALIBRATION__;
let __5ehubProfile=__5ehubWeaponProfiles.weapon_ak47;
let __5ehubProfileName="weapon_ak47";
function __5ehubSelectProfile(weapon){
    const nativeName=weapon?.GetData()?.GetName();
    const scoped=weapon?.GetOwner?.()?.IsScoped?.()??false;
    const name=scoped&&__5ehubWeaponProfiles[nativeName+"_scoped"]?nativeName+"_scoped":nativeName,profile=__5ehubWeaponProfiles[name];
    const selected=profile?.recoil?.length&&(!profile.silenced||weapon.IsSilencerOn())?profile:undefined;
    if(name!==__5ehubProfileName||selected!==__5ehubProfile){
        if(__5ehubProfileName?.replace(/_scoped$/,"")!==nativeName||!selected)__5ehubRmResetShots();
        __5ehubProfileName=name;__5ehubProfile=selected;
    }
    return selected;
}
const __5ehubRmDotModel = "models/ulletical/recoil_master/patterns/dot_single_001.vmdl";
const __5ehubRmDotStyles = {
    path: { color: {r:255,g:0,b:0,a:255}, scale:.65 },
    focus: { color: {r:0,g:255,b:0,a:255}, scale:1 },
    previous: { color: {r:100,g:100,b:100,a:255}, scale:.5 },
    next: { color: {r:205,g:92,b:92,a:220}, scale:.8 },
    hidden: { color: {r:255,g:0,b:0,a:0}, scale:.65 }
};
let __5ehubRmMarkers=[], __5ehubRmMarkerStyles=[], __5ehubRmCreating;
let __5ehubRmRoundActive=false, __5ehubRmGuideEnabled=true, __5ehubAuto=false, __5ehubGuideStarted=false;
let __5ehubGuideWhen="always",__5ehubRoundFired=false;
function __5ehubSetGuideWhen(value){
    if(!["always","fire","visible"].includes(value))return false;
    __5ehubGuideWhen=value;return true;
}
let __5ehubScreenShake=false;
function __5ehubSetScreenShake(enabled){__5ehubScreenShake=!!enabled;Command("view_punch_decay "+(__5ehubScreenShake?18:10000));}
let __5ehubRmPart="head", __5ehubRmShotCount=0, __5ehubRmLastShotTime;
let __5ehubFireRecord, __5ehubLastRender, __5ehubReloadUntil=0;
let __5ehubDisplay="world",__5ehubViewport=__VIEWPORT__;
function __5ehubDrawingVersion(){return __5ehubDisplay==="screen"?1:2;}
function __5ehubSetDrawingVersion(version){
    if(version!==1&&version!==2)return false;
    __5ehubDisplay=version===1?"screen":"world";
    __5ehubCueDisplay="world";
    __5ehubRmHide();
    Instance.Msg("[AK-DRAWING] version="+version);
    return true;
}
// HUD input-error diagnostic failed visual validation. Production/default
// stays on the target-following world renderer; never enable HUD implicitly.
let __5ehubCueDisplay="world";
let __5ehubAlignSamples=[];
let __5ehubTestSettings;
let __5ehubViewDelta={pitch:0,yaw:0,updated:0,velocityPitch:0,velocityYaw:0};
let __5ehubCameraProbe=false,__5ehubCameraFollowProbe=false;
function __5ehubCameraProbeTick(){
    if(!__5ehubCameraProbe)return;
    const pawn=__5ehubRmFindHuman();if(!pawn)return;
    const camera=getCamera(pawn);if(!camera?.IsValid())return;
    if(__5ehubCameraFollowProbe&&typeof camera.SetFollowConfig==="function"){
        camera.SetFollowConfig({followEntity:pawn,followEyes:true,followOffset:{x:0,y:0,z:0},cameraOffset:{x:0,y:0,z:0},clipCameraOffset:false});
        camera.SetMode(CustomCameraMode.FOLLOW_POSITION);return;
    }
    // With a custom camera enabled, EyePosition refers to that camera. Sample
    // the physical eye while temporarily disabled, then publish only the final
    // enabled state after this callback; no client frame sees the intermediate.
    setCameraEnabled(pawn,false);
    const position=pawn.GetEyePosition(),angles=pawn.GetEyeAngles();
    // Seed the camera before enabling it: an uninitialized camera is at 0,0,0.
    camera.Teleport({position,angles});
    setCameraEnabled(pawn,true);setCameraControllingAngles(pawn,false);
}
let __5ehubStats={shots:0,impacts:0,hits:0,maxError:0,sumError2:0};
const __5ehubDepth=64, __5ehubReferenceDistance=478;
function __5ehubRmWrap(a){return ((a+180)%360+360)%360-180;}
function __5ehubRmAngles(v){return {pitch:Math.atan2(-v.z,Math.hypot(v.x,v.y))*180/Math.PI,yaw:Math.atan2(v.y,v.x)*180/Math.PI,roll:0};}
function __5ehubRmDirection(a){const p=a.pitch*Math.PI/180,y=a.yaw*Math.PI/180;return {x:Math.cos(p)*Math.cos(y),y:Math.cos(p)*Math.sin(y),z:-Math.sin(p)};}
function __5ehubDelta(a,b){return {x:a.x-b.x,y:a.y-b.y,z:a.z-b.z};}
function __5ehubRmFindHuman(){
    const pawn=PlayerMgr.resolveUser()?.getPawn();
    return pawn?.IsValid()&&pawn.IsAlive()?pawn:undefined;
}
function __5ehubFindTarget(human){
    const selected=peekMode.victim;
    if(selected?.IsValid())return selected.IsAlive()?selected:undefined;
    for(const controller of Instance.GetAllPlayerControllers()){
        if(!controller.IsConnected()||!controller.IsBot())continue;
        const bot=controller.GetPlayerPawn();
        if(bot?.IsValid()&&bot.IsAlive()&&bot.GetTeamNumber()!==human.GetTeamNumber())return bot;
    }
    return undefined;
}
function __5ehubRmAnchor(bot){const p=bot.GetEyePosition();return {x:p.x,y:p.y,z:p.z+(__5ehubRmPart==="chest"?-25:__5ehubRmPart==="neck"?-12:0)};}
function __5ehubCanSeeBot(human,bot,eye,view){
    // Check several body heights: a head-only peek or exposed legs should
    // count even when the selected training anchor is behind cover.
    const head=bot.GetEyePosition();
    for(const offset of [0,-25,-42,-56]){
        const point={x:head.x,y:head.y,z:head.z+offset};
        const screen=__5ehubScreenPoint(__5ehubDelta(point,eye),view);
        if(!screen||screen.x<0||screen.x>1||screen.y<0||screen.y>1)continue;
        const trace=Instance.TraceLine({start:eye,end:point,ignoreEntity:human,traceHitboxes:true});
        if(trace&&!trace.startedInSolid&&(trace.hitEntity===bot||(!trace.didHit&&trace.fraction>=.999)))return true;
    }
    return false;
}
function __5ehubAim(eye,target,index){
    const a=__5ehubRmAngles(__5ehubDelta(target,eye)),table=__5ehubProfile.recoil,r=table[Math.min(index,table.length-1)];
    return {pitch:a.pitch-r.pitch,yaw:__5ehubRmWrap(a.yaw-r.yaw),roll:0};
}
function __5ehubDisplayAim(eye,target,index){
    const aim=__5ehubAim(eye,target,index);
    // Each point has its own measured, immutable first-person correction.
    // Never add the current shot's camera punch to the entire reference.
    const correction=__5ehubDisplayCalibration[__5ehubProfileName]?.[index];
    return correction?{pitch:aim.pitch+correction.pitch,yaw:__5ehubRmWrap(aim.yaw+correction.yaw),roll:0}:aim;
}
function __5ehubCurrentDisplayAim(eye,target,index){
    // Only the active cue needs the current native camera offset. Future red
    // references keep their immutable per-point display calibration.
    if(__5ehubGuideStarted&&Date.now()/1000-__5ehubViewDelta.updated<.2){
        const aim=__5ehubAim(eye,target,index);
        // Extrapolate only the measured camera offset over transport delay.
        // Reference geometry and bullet compensation remain unchanged.
        const age=Math.max(0,Math.min(.12,Date.now()/1000-__5ehubViewDelta.updated));
        const pitch=__5ehubViewDelta.pitch+(__5ehubViewDelta.velocityPitch??0)*age;
        const yaw=__5ehubViewDelta.yaw+(__5ehubViewDelta.velocityYaw??0)*age;
        return {pitch:aim.pitch+pitch,yaw:__5ehubRmWrap(aim.yaw+yaw),roll:0};
    }
    return __5ehubDisplayAim(eye,target,index);
}
function __5ehubScreenPoint(ray,view){
    const p=view.pitch*Math.PI/180,y=view.yaw*Math.PI/180,f=__5ehubRmDirection(view);
    const depth=ray.x*f.x+ray.y*f.y+ray.z*f.z;
    if(depth<=.25)return undefined;
    const right=ray.x*Math.sin(y)-ray.y*Math.cos(y);
    const up=ray.x*Math.sin(p)*Math.cos(y)+ray.y*Math.sin(p)*Math.sin(y)+ray.z*Math.cos(p);
    const aspect=__5ehubViewport.width/__5ehubViewport.height;
    const span=1.5*Math.tan((__5ehubProfile?.fov4by3??90)*Math.PI/360);
    return {x:.5+right/(depth*span*aspect),y:.5-up/(depth*span)};
}
function __5ehubSetViewport(width,height){
    const w=Number(width),h=Number(height);
    if(!Number.isInteger(w)||!Number.isInteger(h)||w<320||h<200||w>16384||h>16384)return false;
    __5ehubViewport={width:w,height:h};
    Instance.Msg("[AK-VIEWPORT] "+w+"x"+h);
    return true;
}
function __5ehubRmResetShots(){__5ehubRmShotCount=0;__5ehubRmLastShotTime=undefined;__5ehubReloadUntil=0;__5ehubFireRecord=undefined;__5ehubGuideStarted=false;}
function __5ehubRmCurrentIndex(now){
    // Keep the last measured reference visible until this target dies.
    return Math.min(__5ehubRmShotCount,__5ehubProfile.recoil.length-1);
}
function __5ehubContinuous(now){return __5ehubRmLastShotTime===undefined||now-__5ehubRmLastShotTime<.16;}
function __5ehubRmSetMarkerStyle(i,state){
    const m=__5ehubRmMarkers[i];if(!m?.IsValid()||__5ehubRmMarkerStyles[i]===state)return;
    const s=__5ehubRmDotStyles[state];m.SetColor(s.color);
    // Preserve RecoilMaster's apparent size at its reference viewing distance.
    m.SetModelScale(s.scale*__5ehubDepth/__5ehubReferenceDistance);
    __5ehubRmMarkerStyles[i]=state;
}
function __5ehubRmHide(){for(let i=0;i<__5ehubRmMarkers.length;i++)__5ehubRmSetMarkerStyle(i,"hidden");}
async function __5ehubRmEnsureMarkers(){
    // Keep the asynchronous initialization contract without creating invisible
    // props. Native overlays are the renderer; no per-tick entity Move is needed.
    __5ehubRmHide();__5ehubRmMarkers=[];__5ehubRmMarkerStyles=[];
    Instance.Msg("[AK-LOCAL] native world drawing ready; marker props skipped");
}
function __5ehubRmRender(){
    const human=__5ehubRmFindHuman(),bot=human?__5ehubFindTarget(human):undefined;
    const profile=human?__5ehubSelectProfile(human.GetActiveWeapon()):undefined;
    if(!__5ehubRmRoundActive||!peekMode.bPeekStatus||ModeMgr.getCurrentModeId()!=="peek"||!human||!bot||!profile){__5ehubRmHide();return;}
    if(__5ehubTestSettings?.probe){
        // Controlled local probe uses the already measured, unobstructed lane.
        // Original peek push volumes must not contaminate a stationary test.
        bot.Teleport({position:{x:-600,y:0,z:0},velocity:{x:0,y:0,z:0}});
    }
    const now=Instance.GetGameTime();
    // A released trigger resets the visual sequence on the next Think.
    // Also handle a held trigger that has stopped producing shots (empty clip).
    if(__5ehubGuideStarted&&(!human.IsInputPressed(CSInputs.ATTACK)||!__5ehubContinuous(now)))__5ehubRmResetShots();
    const eye=human.GetEyePosition(),target=__5ehubRmAnchor(bot),index=__5ehubRmCurrentIndex(now);
    if(index===undefined){__5ehubRmHide();return;}
    const aim=__5ehubAim(eye,target,index);
    const aimApplied=__5ehubAuto&&__5ehubGuideStarted&&__5ehubRmShotCount<profile.recoil.length&&now>=__5ehubReloadUntil&&__5ehubContinuous(now);
    if(aimApplied)human.SetEyeAngles(aim);
    const view=human.GetEyeAngles();
    const cameraView=Date.now()/1000-__5ehubViewDelta.updated<.2?{pitch:view.pitch+__5ehubViewDelta.pitch,yaw:__5ehubRmWrap(view.yaw+__5ehubViewDelta.yaw),roll:0}:view;
    const botVisible=__5ehubRmGuideEnabled&&__5ehubGuideWhen==="visible"?__5ehubCanSeeBot(human,bot,eye,cameraView):undefined;
    const showGuide=__5ehubRmGuideEnabled&&(__5ehubGuideWhen==="always"||(__5ehubGuideWhen==="fire"?__5ehubRoundFired:botVisible));
    const targetDelta=__5ehubDelta(target,eye);
    // Reference geometry depends on the target and compensation table only.
    // Neither live camera punch nor looking around can move it relative to Bot.
    const targetDistance=Math.hypot(targetDelta.x,targetDelta.y,targetDelta.z);
    // Version 1 reproduces all-weapons-2's view-facing 64-unit plane and
    // uncorrected screen projection. Version 2 keeps the current world path.
    const normal=__5ehubDisplay==="screen"?__5ehubRmDirection(view):__5ehubRmDirection(__5ehubRmAngles(targetDelta));
    const drawDepth=__5ehubDisplay==="screen"?__5ehubDepth:Math.max(__5ehubDepth,targetDistance);
    const displayView=view;
    const displayAim=__5ehubDisplay==="world"?__5ehubCurrentDisplayAim(eye,target,index):aim;
    const cameraDelta={pitch:displayAim.pitch-aim.pitch,yaw:__5ehubRmWrap(displayAim.yaw-aim.yaw)};
    let focus;
    let visible=0;
    for(let i=0;i<profile.recoil.length;i++){
        // Consumed points are removed, rather than retained as grey history.
        if(i<index)continue;
        const pointAim=__5ehubDisplay==="world"?(i===index?displayAim:__5ehubDisplayAim(eye,target,i)):__5ehubAim(eye,target,i);
        const ray=__5ehubRmDirection(pointAim),dot=ray.x*normal.x+ray.y*normal.y+ray.z*normal.z;
        if(!showGuide||dot<=.25)continue;
        const t=drawDepth/dot;
        const position={x:eye.x+ray.x*t,y:eye.y+ray.y*t,z:eye.z+ray.z*t};
        const state=i<index?"previous":i===index?"focus":i===index+1?"next":"path";
        // Native drawing is visible in this Workshop scene; the copied prop
        // model is not. Keep the fixed calibrated ray and original colours.
        const style=__5ehubRmDotStyles[state];
        if(state==="focus"&&__5ehubCueDisplay==="hud"){
            // A screen-space INPUT guide: project the required mouse angle
            // against the actual input angle. Automatic aim has zero error;
            // manual aim keeps its real error, without client camera polling.
            const screen=__5ehubScreenPoint(__5ehubRmDirection(aim),view);
            if(screen&&screen.x>=0&&screen.x<=1&&screen.y>=0&&screen.y<=1){
                const projected={x:screen.x*__5ehubViewport.width,y:screen.y*__5ehubViewport.height};
                const draw={x:projected.x-3,y:projected.y};
                focus={projected,draw,inputDelta:{pitch:__5ehubRmWrap(aim.pitch-view.pitch),yaw:__5ehubRmWrap(aim.yaw-view.yaw)}};
                Instance.DebugScreenText({...draw,text:"●",duration:0,color:style.color});visible++;
            }
            continue;
        }
        if(__5ehubDisplay==="screen"){
            const screen=__5ehubScreenPoint(ray,view);
            if(screen&&screen.x>=0&&screen.x<=1&&screen.y>=0&&screen.y<=1){
                const projected={x:screen.x*__5ehubViewport.width,y:screen.y*__5ehubViewport.height};
                // Keep the native glyph baseline at the projected Y coordinate.
                // The previous -6 shift placed the green cue above the crosshair.
                const draw={x:projected.x-3,y:projected.y};
                if(state==="focus")focus={projected,draw,projectionDelta:{x:projected.x-__5ehubViewport.width/2,y:projected.y-__5ehubViewport.height/2},drawOffset:{x:-3,y:0}};
                Instance.DebugScreenText({...draw,text:state==="focus"?"●":"•",duration:0,color:style.color});
            }
        }else{
            const radius=2*style.scale*drawDepth/__5ehubReferenceDistance;
            if(state==="focus")focus={center:position,radius};
            Instance.DebugSphere({center:position,radius,duration:0,color:style.color});
        }
        visible++;
    }
    __5ehubLastRender={time:now,index,weapon:__5ehubProfileName,pointCount:profile.recoil.length,eye,target,aim,view,displayAim,displayView,cameraDelta:{pitch:cameraDelta.pitch,yaw:cameraDelta.yaw},cameraProbe:__5ehubCameraProbe,visible,auto:__5ehubAuto,aimApplied,guide:__5ehubRmGuideEnabled,guideWhen:__5ehubGuideWhen,roundFired:__5ehubRoundFired,botVisible,showGuide,display:__5ehubDisplay,drawingVersion:__5ehubDrawingVersion(),cueDisplay:__5ehubCueDisplay,drawDepth,viewport:__5ehubViewport,focus};
    if(aimApplied&&focus&&(now-(__5ehubAlignSamples.at(-1)?.time??-1)>.08)){
        __5ehubAlignSamples.push({time:now,index,angleDelta:{pitch:__5ehubRmWrap(view.pitch-aim.pitch),yaw:__5ehubRmWrap(view.yaw-aim.yaw)},...focus});
        if(__5ehubAlignSamples.length>30)__5ehubAlignSamples.shift();
    }
}
function __5ehubRmStartRound(){
    __5ehubRmResetShots();__5ehubRoundFired=false;__5ehubStats={shots:0,impacts:0,hits:0,maxError:0,sumError2:0};
    __5ehubRmRoundActive=true;
    Command("bot_dont_shoot 1");
}
function __5ehubRmStopRound(){__5ehubRmRoundActive=false;__5ehubRoundFired=false;__5ehubRmResetShots();__5ehubRmHide();}
function __5ehubRmConsoleCommand(name,fn){try{Instance.RegisterCheatCommand(name,fn);}catch(e){Instance.Msg("[AK-LOCAL] command error "+name+": "+String(e));}}
__5ehubRmConsoleCommand("akauto",args=>{__5ehubAuto=args.trim()==="on";Instance.Msg("[AK-LOCAL] auto="+__5ehubAuto);});
__5ehubRmConsoleCommand("akguide",args=>{__5ehubRmGuideEnabled=args.trim()!=="off";if(!__5ehubRmGuideEnabled)__5ehubRmHide();});
__5ehubRmConsoleCommand("akguidewhen",args=>__5ehubSetGuideWhen(args.trim()));
__5ehubRmConsoleCommand("akshake",args=>__5ehubSetScreenShake(args.trim()==="on"));
__5ehubRmConsoleCommand("akanchor",args=>{const p=args.trim();if(["head","neck","chest"].includes(p))__5ehubRmPart=p;});
__5ehubRmConsoleCommand("akdisplay",args=>__5ehubSetDrawingVersion(args.trim()==="screen"?1:2));
__5ehubRmConsoleCommand("akversion",args=>__5ehubSetDrawingVersion(Number(args.trim())));
__5ehubRmConsoleCommand("akcue",args=>{__5ehubCueDisplay=args.trim()==="hud"?"hud":"world";});
__5ehubRmConsoleCommand("akviewdelta",args=>{
    const [pitch,yaw,velocityPitch=0,velocityYaw=0,captured]=args.trim().split(/\s+/).map(Number);
    const now=Date.now()/1000;
    if(Number.isFinite(pitch)&&Number.isFinite(yaw)&&Math.abs(pitch)<40&&Math.abs(yaw)<40&&Number.isFinite(velocityPitch)&&Number.isFinite(velocityYaw)&&Math.abs(velocityPitch)<=35&&Math.abs(velocityYaw)<=35){
        const updated=Number.isFinite(captured)&&Math.abs(now-captured)<1?captured:now;
        __5ehubViewDelta={pitch,yaw,velocityPitch,velocityYaw,updated};
    }
});
__5ehubRmConsoleCommand("akcamera",args=>{
    if(args.trim()==="info"){probeCameraApi();return;}
    __5ehubCameraProbe=args.trim()==="on"||args.trim()==="follow";
    __5ehubCameraFollowProbe=args.trim()==="follow";
    if(!__5ehubCameraProbe){const pawn=__5ehubRmFindHuman();if(pawn)setCameraEnabled(pawn,false);}
    Instance.Msg("[AK-CAMERA] local camera probe="+__5ehubCameraProbe);
});
__5ehubRmConsoleCommand("akviewport",args=>{const [w,h]=args.trim().split(/\s+/);__5ehubSetViewport(w,h);});
async function __5ehubEquipWeapon(name){
    if(!__5ehubWeaponProfiles[name]?.recoil.length)return false;
    const player=PlayerMgr.resolveUser();if(!player)return false;
    __5ehubRmResetShots();await player.updateWeapon(name);
    const pawn=player.getPawn(),equipped=pawn?.FindWeapon?.(name);
    if(equipped)pawn.SwitchToWeapon(equipped);
    __5ehubSelectProfile(pawn?.GetActiveWeapon());
    return true;
}
__5ehubRmConsoleCommand("akweapon",args=>{
    const value=args.trim(),aliases={ak:"weapon_ak47",ak47:"weapon_ak47",m4a1:"weapon_m4a1_silencer",m4a1s:"weapon_m4a1_silencer",m4a4:"weapon_m4a1",galil:"weapon_galilar",galilar:"weapon_galilar"};
    __5ehubEquipWeapon(aliases[value]||value).catch(e=>Instance.Msg("[GUN-GUIDE] equip error="+String(e)));
});
__5ehubRmConsoleCommand("akenter",()=>{
    ModeMgr.switchTo("peek");
    Instance.Delay(1).then(()=>{
        _teleport_mode("peek");
        const human=__5ehubRmFindHuman();if(human)__5ehubSelectProfile(human.GetActiveWeapon());
    }).catch(e=>Instance.Msg("[AK-LOCAL] enter error="+String(e)));
});
__5ehubRmConsoleCommand("akdebug",()=>{
    const human=__5ehubRmFindHuman(),bot=peekMode.victim;
    const trace=human&&bot?.IsValid()?Instance.TraceLine({start:human.GetEyePosition(),end:__5ehubRmAnchor(bot),ignoreEntity:human,traceHitboxes:true}):undefined;
    Instance.Msg("[AK-STATE] "+JSON.stringify({active:__5ehubRmRoundActive,mode:ModeMgr.getCurrentModeId(),weapon:human?.GetActiveWeapon()?.GetData()?.GetName(),scoped:human?.IsScoped(),guide:__5ehubRmGuideEnabled,screenShake:__5ehubScreenShake,render:__5ehubLastRender,stats:__5ehubStats,bot:bot?.IsValid()?{origin:bot.GetAbsOrigin(),velocity:bot.GetAbsVelocity(),health:bot.GetHealth(),alive:bot.IsAlive()}:undefined,ammo:human?.GetActiveWeapon()?.GetClipAmmo(),trace:trace?{hitBot:trace.hitEntity===bot,group:trace.hitGroup,fraction:trace.fraction}:undefined,marker:__5ehubRmMarkers[0]?.IsValid()?__5ehubRmMarkers[0].GetAbsOrigin():undefined}));
});
__5ehubRmConsoleCommand("akalign",()=>Instance.Msg("[AK-ALIGN] "+JSON.stringify(__5ehubAlignSamples)));
__5ehubRmConsoleCommand("aktest",args=>{
    if(args.trim()==="stop"){
        if(__5ehubTestSettings){
            if(__5ehubTestSettings.probe){
                const human=__5ehubRmFindHuman(),saved=__5ehubTestSettings.probe;
                human?.Teleport({position:saved.origin,velocity:{x:0,y:0,z:0}});
                human?.SetEyeAngles(saved.view);
                if(peekMode.victim?.IsValid())peekMode.victim.Teleport({position:saved.botOrigin,velocity:{x:0,y:0,z:0}});
            }
            Settings.set("accuracyNospread",__5ehubTestSettings.noSpread);
            Command("sv_infinite_ammo "+__5ehubTestSettings.infBullet);
            __5ehubAuto=__5ehubTestSettings.auto;__5ehubRmPart=__5ehubTestSettings.part;
            peekMode.peekMode=__5ehubTestSettings.peekMode;
            peekMode.iBotSpawnHeightLow=__5ehubTestSettings.heightLow;
            peekMode.iBotSpawnHeightHigh=__5ehubTestSettings.heightHigh;
            PlayerMgr.setBotHP(Settings.get("botHP"));__5ehubTestSettings=undefined;
        }
        __5ehubRmResetShots();return;
    }
    if(!__5ehubTestSettings)__5ehubTestSettings={noSpread:Settings.get("accuracyNospread"),infBullet:Settings.get("infBullet"),auto:__5ehubAuto,part:__5ehubRmPart,peekMode:peekMode.peekMode,heightLow:peekMode.iBotSpawnHeightLow,heightHigh:peekMode.iBotSpawnHeightHigh};
    const [part,testMode]=args.trim().split(/\s+/);
    if(testMode==="static"||testMode==="moving"){
        // Use the map's native platform and spawn flow, above its low cover.
        peekMode.peekMode=testMode==="static"?PeekModeType.static:PeekModeType.dynamic;
        peekMode.iBotSpawnHeightLow=224;peekMode.iBotSpawnHeightHigh=224;
        peekMode.peekChoose();
    }
    if(!__5ehubRmRoundActive)peekMode.peekChoose();
    if(testMode==="probe"&&!__5ehubTestSettings.probe){
        const human=__5ehubRmFindHuman(),bot=peekMode.victim;
        if(human&&bot?.IsValid()){
            __5ehubTestSettings.probe={origin:human.GetAbsOrigin(),view:human.GetEyeAngles(),botOrigin:bot.GetAbsOrigin()};
            human.Teleport({position:{x:96,y:0,z:0},velocity:{x:0,y:0,z:0}});
            bot.Teleport({position:{x:-600,y:0,z:0},velocity:{x:0,y:0,z:0}});
        }
    }
    const bot=peekMode.victim;if(bot?.IsValid()){bot.SetMaxHealth(100000);bot.SetHealth(100000);}
    Settings.set("accuracyNospread",true);Settings.set("botDontshoot",true);
    __5ehubRmPart=part==="head"?"head":"chest";__5ehubAuto=true;__5ehubRmResetShots();
    const human=__5ehubRmFindHuman(),w=human?.GetActiveWeapon();
    if(w&&__5ehubSelectProfile(w)){
        w.SetClipAmmo(w.GetData().GetMaxClipAmmo());
        if(bot?.IsAlive())human.SetEyeAngles(__5ehubAim(human.GetEyePosition(),__5ehubRmAnchor(bot),0));
    }
});
// Wrap existing PeekMode lifecycle methods; keep its native event dispatch.
const __5ehubOriginalPeekChoose=peekMode.peekChoose.bind(peekMode);
peekMode.peekChoose=function(...args){__5ehubRmStopRound();const r=__5ehubOriginalPeekChoose(...args);if(this.bPeekStatus&&this.victim?.IsValid())__5ehubRmStartRound();return r;};
const __5ehubOriginalPeekKill=peekMode.onPlayerKill.bind(peekMode);
peekMode.onPlayerKill=function(...args){__5ehubRmStopRound();return __5ehubOriginalPeekKill(...args);};
const __5ehubOriginalPeekExit=peekMode.onExit.bind(peekMode);
peekMode.onExit=function(...args){__5ehubRmStopRound();return __5ehubOriginalPeekExit(...args);};
eventBus.on(GameEvents.GUN_FIRE,(controller,name)=>{
    const human=__5ehubRmFindHuman();if(ModeMgr.getCurrentModeId()!=="peek"||!peekMode.bPeekStatus||!__5ehubRmRoundActive||!human||controller?.IsBot()||controller?.GetPlayerSlot()!==human.GetOriginalPlayerController().GetPlayerSlot())return;
    if(name!==human.GetActiveWeapon()?.GetData()?.GetName()||!__5ehubSelectProfile(human.GetActiveWeapon()))return;
    const bot=__5ehubFindTarget(human);if(!bot)return;
    const now=Instance.GetGameTime();if(__5ehubRmLastShotTime!==undefined&&now-__5ehubRmLastShotTime>.16)__5ehubRmResetShots();
    if(!__5ehubRmRoundActive)__5ehubRmRoundActive=true;
    __5ehubGuideStarted=true;__5ehubRoundFired=true;
    __5ehubFireRecord={weapon:name,profile:__5ehubProfileName,eye:human.GetEyePosition(),view:human.GetEyeAngles(),index:__5ehubRmShotCount,target:__5ehubRmAnchor(bot),bot,consumed:false};
    __5ehubRmShotCount++;__5ehubRmLastShotTime=now;__5ehubStats.shots++;
});
Instance.OnBulletImpact(({weapon,position,hitEntity})=>{
    if(typeof __5ehubCalibrationImpact==="function"&&__5ehubCalibrationImpact({weapon,position,hitEntity}))return;
    const human=__5ehubRmFindHuman();if(!human||weapon.GetOwner()!==human)return;
    const impactEye=human.GetEyePosition(),impactView=human.GetEyeAngles();
    Instance.QueueAfterThinks(()=>{
        const record=__5ehubFireRecord;if(!record||record.consumed||record.weapon!==weapon.GetData().GetName())return;record.consumed=true;
        const actual=__5ehubRmAngles(__5ehubDelta(position,record.eye)),desired=__5ehubRmAngles(__5ehubDelta(record.target,record.eye));
        const error=Math.hypot(__5ehubRmWrap(actual.pitch-desired.pitch),__5ehubRmWrap(actual.yaw-desired.yaw));
        const impactRay=__5ehubRmAngles(__5ehubDelta(position,impactEye));
        const observedRecoil={pitch:__5ehubRmWrap(impactRay.pitch-impactView.pitch),yaw:__5ehubRmWrap(impactRay.yaw-impactView.yaw)};
        const expectedRecoil=__5ehubWeaponProfiles[record.profile]?.recoil[record.index];
        const recoilError=expectedRecoil?Math.hypot(observedRecoil.pitch-expectedRecoil.pitch,observedRecoil.yaw-expectedRecoil.yaw):undefined;
        __5ehubStats.impacts++;__5ehubStats.sumError2+=error*error;__5ehubStats.maxError=Math.max(error,__5ehubStats.maxError);
        if(hitEntity===record.bot)__5ehubStats.hits++;
        Instance.Msg("[AK-IMPACT] "+JSON.stringify({weapon:record.weapon,profile:record.profile,shot:record.index+1,error,recoilError,observedRecoil,hitBot:hitEntity===record.bot,actual,desired,position}));
    });
});
Instance.OnGunReload(({weapon})=>{if(weapon.GetOwner()!==__5ehubRmFindHuman())return;__5ehubRmResetShots();__5ehubReloadUntil=Instance.GetGameTime()+2.5;});
Instance.OnPlayerChat(({player,text})=>{
    if(player?.IsBot())return;const [cmd,value]=text.trim().toLowerCase().split(/\s+/);
    if(cmd==="!akauto")__5ehubAuto=value==="on";
    if(cmd==="!akguide")__5ehubRmGuideEnabled=value!=="off";
    if(cmd==="!akpart"&&["head","neck","chest"].includes(value))__5ehubRmPart=value;
});
// Disable the original right-click aim only while this verification mode owns aim.
const __5ehubOriginalAutoTick=AutoAim.tick.bind(AutoAim);
AutoAim.tick=function(){if(!(__5ehubAuto&&__5ehubRmRoundActive&&peekMode.bPeekStatus))__5ehubOriginalAutoTick();};
Instance.Msg("[AK-LOCAL] measured weapon guides and local auto test installed");
// Preserve the user's successful local test of reduced visual view-punch.
__5ehubSetScreenShake(false);
