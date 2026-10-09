// Local development rig: observe actual bullet rays with spread disabled.
let __5ehubCalibration;
let __5ehubCalibrationResult;
function __5ehubCalibrationLog(record){Instance.Msg("[WEAPON-CAL] "+JSON.stringify(record));}
function __5ehubCalibrationTick(){
    const rig=__5ehubCalibration;if(!rig)return false;
    const pawn=__5ehubRmFindHuman();if(!pawn)return true;
    // Never teleport or overwrite eye angles while firing: doing so changes
    // the recoil state we are trying to observe.
    if(!rig.ready){pawn.Teleport({position:rig.origin,velocity:{x:0,y:0,z:0}});pawn.SetEyeAngles(rig.view);}
    return true;
}
function __5ehubCalibrationImpact(event){
    const rig=__5ehubCalibration;if(!rig)return false;
    const pawn=__5ehubRmFindHuman();
    if(!rig.ready||!pawn||event.weapon.GetOwner()!==pawn||event.weapon.GetData().GetName()!==rig.weapon)return true;
    const eye=pawn.GetEyePosition(),view=pawn.GetEyeAngles();
    const actual=__5ehubRmAngles(__5ehubDelta(event.position,eye));
    // Native impacts can arrive before the same tick's gun-fire event.
    // Snapshot geometry now, then pair with that event after Think dispatch.
    Instance.QueueAfterThinks(()=>{
    const fire=rig.fire;if(__5ehubCalibration!==rig||!fire||fire.consumed)return;
    fire.consumed=true;
    const record={event:"sample",weapon:rig.profile,nativeWeapon:rig.weapon,scoped:pawn.IsScoped(),run:rig.run,shot:fire.shot,time:fire.time,
        pitch:__5ehubRmWrap(actual.pitch-view.pitch),yaw:__5ehubRmWrap(actual.yaw-view.yaw),
        silenced:event.weapon.IsSilencerOn(),eye,view,impact:event.position};
    rig.records.push(record);__5ehubCalibrationLog(record);
    if(rig.records.length===rig.count){
        rig.ready=false;event.weapon.SetClipAmmo(0);event.weapon.SetReserveAmmo(0);
        __5ehubCalibrationResult={weapon:rig.profile,run:rig.run,count:rig.count,records:rig.records};
        __5ehubCalibrationLog({event:"done",weapon:rig.profile,run:rig.run,count:rig.records.length});
    }
    });
    return true;
}
const __5ehubUncalibratedRender=__5ehubRmRender;
__5ehubRmRender=function(){if(!__5ehubCalibrationTick())__5ehubUncalibratedRender();};
const __5ehubUncalibratedAutoTick=AutoAim.tick.bind(AutoAim);
AutoAim.tick=function(){if(!__5ehubCalibration)__5ehubUncalibratedAutoTick();};
eventBus.on(GameEvents.GUN_FIRE,(controller,name)=>{
    const rig=__5ehubCalibration,pawn=__5ehubRmFindHuman();
    if(!rig?.ready||!pawn||controller?.IsBot()||controller?.GetPlayerSlot()!==pawn.GetOriginalPlayerController().GetPlayerSlot()||name!==rig.weapon)return;
    rig.shots++;
    rig.fire={shot:rig.shots,time:Instance.GetGameTime(),consumed:false};
});
async function __5ehubCalibrationStart(weapon,run){
    const spec=__5ehubWeaponCatalog.find(p=>p.key===weapon);
    if(!spec)throw Error("Unsupported calibration weapon");
    const player=PlayerMgr.resolveUser(),pawn=player?.getPawn();if(!pawn?.IsAlive())throw Error("No live player");
    if(__5ehubCalibration)throw Error("Cancel previous calibration first");
    const rig={weapon:spec.nativeWeapon,profile:spec.key,run:run||"1",origin:{x:96,y:0,z:0},view:{pitch:0,yaw:180,roll:0},ready:false,shots:0,records:[],
        saved:{origin:pawn.GetAbsOrigin(),weapon:player.primaryWeapon,secondary:player.secondaryWeapon,view:pawn.GetEyeAngles(),noSpread:Settings.get("accuracyNospread"),infBullet:Settings.get("infBullet"),screenShake:__5ehubScreenShake,auto:__5ehubAuto,bots:[]}};
    __5ehubCalibration=rig;__5ehubAuto=false;__5ehubRmResetShots();
    __5ehubSetScreenShake(false);
    player.ui?.hide();
    Settings.set("accuracyNospread",true);Settings.set("infBullet",0);
    Command("host_timescale 1; bot_dont_shoot 1");
    for(const controller of Instance.GetAllPlayerControllers()){
        const bot=controller.IsBot()?controller.GetPlayerPawn():undefined;
        if(bot?.IsAlive()){rig.saved.bots.push({bot,max:bot.GetMaxHealth(),health:bot.GetHealth()});bot.SetMaxHealth(100000);bot.SetHealth(100000);}
    }
    await player.updateWeapon(spec.nativeWeapon);
    await Instance.Delay(2.8);
    if(__5ehubCalibration!==rig)return;
    const requested=pawn.FindWeapon(spec.nativeWeapon);if(requested)pawn.SwitchToWeapon(requested);
    await Instance.Delay(.4);
    __5ehubCalibrationLog({event:"equipped",weapon:rig.profile,run:rig.run,scoped:spec.scoped,actualWeapon:pawn.GetActiveWeapon()?.GetData().GetName(),actualScope:pawn.IsScoped()});
    for(let i=0;pawn.IsScoped()!==spec.scoped&&i<50;i++)await Instance.Delay(.1);
    if(__5ehubCalibration!==rig)return;
    const active=pawn.GetActiveWeapon();
    if(active?.GetData().GetName()!==spec.nativeWeapon||pawn.IsScoped()!==spec.scoped)throw Error("Requested weapon/scope was not equipped: "+JSON.stringify({actualWeapon:active?.GetData().GetName(),actualScope:pawn.IsScoped(),expectedWeapon:spec.nativeWeapon,expectedScope:spec.scoped}));
    await Instance.Delay(.4);
    if(__5ehubCalibration!==rig)return;
    rig.count=active.GetData().GetMaxClipAmmo();
    active.SetClipAmmo(rig.count);active.SetReserveAmmo(0);rig.ready=true;
    __5ehubCalibrationLog({event:"ready",weapon:rig.profile,nativeWeapon:rig.weapon,scoped:pawn.IsScoped(),run:rig.run,count:rig.count,silenced:active.IsSilencerOn(),eye:pawn.GetEyePosition(),view:pawn.GetEyeAngles()});
}
async function __5ehubCalibrationCancel(){
    const rig=__5ehubCalibration;if(!rig)return;
    __5ehubCalibration=undefined;
    Settings.set("accuracyNospread",rig.saved.noSpread);Settings.set("infBullet",rig.saved.infBullet);
    __5ehubAuto=rig.saved.auto;__5ehubRmResetShots();
    __5ehubSetScreenShake(rig.saved.screenShake);
    for(const entry of rig.saved.bots)if(entry.bot.IsValid()&&entry.bot.IsAlive()){entry.bot.SetMaxHealth(entry.max);entry.bot.SetHealth(entry.health);}
    const player=PlayerMgr.resolveUser();
    if(player){player.setSecondaryWeapon(rig.saved.secondary);Settings.set("secondaryWeapon",rig.saved.secondary);await player.updateWeapon(rig.saved.weapon);player.getPawn()?.Teleport({position:rig.saved.origin,velocity:{x:0,y:0,z:0}});player.getPawn()?.SetEyeAngles(rig.saved.view);}
    __codexApplyBulletTime();
    __5ehubCalibrationLog({event:"cancelled",weapon:rig.weapon,run:rig.run});
}
__5ehubRmConsoleCommand("akcalibrate",args=>{
    const [weapon,run]=args.trim().split(/\s+/);
    const action=weapon==="cancel"?__5ehubCalibrationCancel():__5ehubCalibrationStart(weapon,run);
    action.catch(error=>{__5ehubCalibrationLog({event:"error",error:String(error)});__5ehubCalibrationCancel();});
});
