const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../src/diagnostics/5ehub-preferences.js'),'utf8');
function rig(saved={}){
    const context=vm.createContext({saved:JSON.stringify(saved),writes:0,logs:[],commands:[],Date,JSON});
    vm.runInContext(`
        let __5ehubRmGuideEnabled=true,__5ehubAuto=false,__5ehubRmPart='head',__5ehubScreenShake=false,__5ehubBotInvincible=false;
        let __5ehubGuideWhen='always',__5ehubViewport={width:1920,height:1080},__codexBulletTimeScale=1,version=2;
        const PeekModeType={static:1,dynamic:2};
        const peekMode={peekMode:2,iBotMoveSpeed:15,iBotSpawnHeightLow:0,iBotSpawnHeightHigh:320,
            iBotSpawnHeightMin:0,iBotSpawnHeightMax:320,bBotSpawnHeightSign:false,nBotSpawnDirection:0,
            nBotSpawnDirectionTypeStatus:[undefined,false,false],peekBotSpawnHeightDisplay(){}};
        const Settings={values:{primaryWeapon:'weapon_ak47',botHP:100,infBullet:1},serialize(){return {...this.values};}};
        const PlayerMgr={resolveUser(){return {};}};
        const Instance={GetSaveData(){return saved;},SetSaveData(value){saved=value;writes++;},Msg(value){logs.push(value);}};
        function saveData(){Instance.SetSaveData(JSON.stringify({...Settings.serialize(),killNum:42,language:'cn'}));}
        async function loadData(){const data=JSON.parse(saved||'{}');for(const key of Object.keys(Settings.values))if(key in data)Settings.values[key]=data[key];}
        function __5ehubSetScreenShake(v){__5ehubScreenShake=v;__5ehubPublishShakeState();}
        function __5ehubSetBotInvincible(v){__5ehubBotInvincible=v;}
        function __5ehubPublishShakeState(){logs.push('shake='+__5ehubScreenShake);}
        function __5ehubSetDrawingVersion(v){version=v;}
        function __5ehubDrawingVersion(){return version;}
        function __5ehubSetGuideWhen(v){__5ehubGuideWhen=v;}
        function __5ehubSetViewport(w,h){if(w>=320&&h>=200&&w<=16384&&h<=16384)__5ehubViewport={width:w,height:h};}
        function __codexSetBulletTime(v){__codexBulletTimeScale=Math.round(Math.max(.1,Math.min(1,v))*100)/100;}
        function EntFire(...args){commands.push(args);}
        function __5ehubRmConsoleCommand(){}
        let _menuProvider=()=>({items:[['test']],onSelect(){__5ehubScreenShake=!__5ehubScreenShake;return false;}});
        function registerMenuProvider(provider){_menuProvider=provider;}
    `,context);
    vm.runInContext(source,context);
    return {context,run:code=>vm.runInContext(code,context),read:()=>JSON.parse(context.saved)};
}
test('all training settings survive a new map session; native weapon/HP/ammo survive too',async()=>{
    const first=rig();await first.run('loadData()');
    first.run(`__5ehubAuto=true;__5ehubRmGuideEnabled=false;__5ehubRmPart='neck';__5ehubSetScreenShake(true);
        __5ehubSetDrawingVersion(1);__5ehubGuideWhen='visible';__5ehubViewport={width:1680,height:1050};__codexBulletTimeScale=.37;
        peekMode.iBotMoveSpeed=35;peekMode.peekMode=1;peekMode.iBotSpawnHeightLow=60;peekMode.iBotSpawnHeightHigh=180;
        peekMode.bBotSpawnHeightSign=true;peekMode.nBotSpawnDirection=4;peekMode.nBotSpawnDirectionTypeStatus=[undefined,true,true];
        Settings.values={primaryWeapon:'weapon_m4a1',botHP:1000,infBullet:2};__codexPreferencesTick(true);`);
    const saved=first.read();assert.equal(saved.killNum,42);assert.equal(saved.language,'cn');
    const next=rig(saved);await next.run('loadData()');
    assert.deepEqual(JSON.parse(next.run('JSON.stringify(__codexCapturePreferences())')),saved.codexRecoilPreferences);
    assert.equal(next.run('Settings.values.primaryWeapon'),'weapon_m4a1');
    assert.equal(next.run('Settings.values.botHP'),1000);
    assert.equal(next.run('Settings.values.infBullet'),2);
    assert.ok(next.context.commands.some(c=>c[0]==='peek_trigger_push_*'&&c[2]==='35'));
});
test('startup save before load never replaces remembered values with defaults',async()=>{
    const saved={codexRecoilPreferences:{schema:1,target:'chest',screenShake:true,bulletTime:.5}};
    const game=rig(saved);game.run('saveData()');
    assert.deepEqual(game.read().codexRecoilPreferences,saved.codexRecoilPreferences);
    await game.run('loadData()');assert.equal(game.run('__5ehubRmPart'),'chest');
});
test('every menu click saves and publishes the selected shake state immediately',async()=>{
    const game=rig();await game.run('loadData()');
    game.run('_menuProvider({}).onSelect(0,0)');
    assert.equal(game.read().codexRecoilPreferences.screenShake,true);
    game.run('_menuProvider({}).onSelect(0,0)');
    assert.equal(game.read().codexRecoilPreferences.screenShake,false);
});
test('Think catches native wall-button changes without saving unchanged ticks',async()=>{
    const game=rig();await game.run('loadData()');
    game.run('__codexPreferencesTick(true)');assert.equal(game.context.writes,0);
    game.run('peekMode.iBotMoveSpeed=20;__codexPreferencesTick(true)');
    assert.equal(game.read().codexRecoilPreferences.peek.speed,20);
    const count=game.context.writes;
    game.run('for(let i=0;i<100;i++)__codexPreferencesTick(true)');assert.equal(game.context.writes,count);
});
test('original periodic saves retain the extension and native statistics',async()=>{
    const game=rig();await game.run('loadData()');
    game.run("__5ehubRmPart='chest';saveData();saveData();");
    assert.equal(game.read().codexRecoilPreferences.target,'chest');assert.equal(game.read().killNum,42);
});
test('old saves remain readable; invalid extension fields fall back individually',async()=>{
    const game=rig({botHP:300,codexRecoilPreferences:{schema:1,target:'invalid',autoAim:'yes',drawingVersion:9,
        screenShake:'yes',guideWhen:'bad',viewport:{width:1,height:1},bulletTime:'oops',peek:{mode:99,speed:-1,heightLow:-5,heightHigh:10000}}});
    await game.run('loadData()');
    assert.equal(game.run('Settings.values.botHP'),300);assert.equal(game.run('__5ehubRmPart'),'head');
    assert.equal(game.run('__5ehubAuto'),false);assert.equal(game.run('version'),2);
    assert.equal(game.run('__codexBulletTimeScale'),1);assert.equal(game.run('peekMode.iBotMoveSpeed'),15);
});
test('saved settings loaded again after a round initialization do not drift',async()=>{
    const game=rig();await game.run('loadData()');
    game.run("__5ehubSetScreenShake(true);__codexPreferencesTick(true);__5ehubScreenShake=false;");
    await game.run('loadData()');assert.equal(game.run('__5ehubScreenShake'),true);
    assert.ok(game.context.logs.includes('shake=true'));
});
test('Bot invincibility survives reload, and old saves default to disabled',async()=>{
    const first=rig();await first.run('loadData()');
    first.run('__5ehubSetBotInvincible(true);__codexPreferencesTick(true)');
    const second=rig(first.read());await second.run('loadData()');
    assert.equal(second.run('__5ehubBotInvincible'),true);
    second.run('__5ehubSetBotInvincible(false);__codexPreferencesTick(true)');
    const third=rig(second.read());await third.run('loadData()');
    assert.equal(third.run('__5ehubBotInvincible'),false);
    const old=rig({codexRecoilPreferences:{schema:1,screenShake:true}});await old.run('loadData()');
    assert.equal(old.run('__5ehubBotInvincible'),false);
});
