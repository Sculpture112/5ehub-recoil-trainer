// Global simulation speed, selected through the existing double-Tab menu.
let __codexBulletTimeScale=1;
function __codexApplyBulletTime(){
    let menuOpen=false;
    PlayerMgr.forEachHuman(p=>{if(p.ui?.isActive())menuOpen=true;});
    const scale=menuOpen?.08:__codexBulletTimeScale;
    Command("host_timescale "+scale.toFixed(2));
    return scale;
}
function __codexSetBulletTime(value){
    const n=Number(value);if(!Number.isFinite(n))return false;
    __codexBulletTimeScale=Math.round(Math.min(1,Math.max(.1,n))*100)/100;
    __codexApplyBulletTime();
    Instance.Msg("[BULLET-TIME] selected="+__codexBulletTimeScale.toFixed(2));
    return true;
}
const __codexOriginalMenuProvider=_menuProvider;
registerMenuProvider(player=>{
    if(player.ui.currentMenuId==="codexBulletTime"){
        const items=[];
        for(let r=0;r<5;r++)items.push([0,1].map(c=>{
            const speed=(r*2+c+1)/10;
            return (Math.abs(speed-__codexBulletTimeScale)<.001?"✓ ":"")+speed.toFixed(1)+"×";
        }));
        items.push(["减速 0.01","加速 0.01"]);
        items.push(["恢复正常 1.0×","返回主菜单"]);
        return {
            title:"子弹时间 · 当前 "+__codexBulletTimeScale.toFixed(2)+"×",
            items,footer:"范围 0.10–1.00×，关闭菜单后应用。",
            onSelect:(row,col)=>{
                if(row>=0&&row<5&&col>=0&&col<2)__codexSetBulletTime((row*2+col+1)/10);
                else if(row===5&&(col===0||col===1))__codexSetBulletTime(__codexBulletTimeScale+(col===0?-.01:.01));
                else if(row===6&&col===0)__codexSetBulletTime(1);
                else if(row===6&&col===1)player.ui.currentMenuId="testMenu";
                return false;
            }
        };
    }
    const data=__codexOriginalMenuProvider(player);
    if(player.ui.currentMenuId!=="testMenu")return data;
    const row=data.items.length,onSelect=data.onSelect;
    return {...data,items:[...data.items,["子弹时间："+__codexBulletTimeScale.toFixed(2)+"×"]],
        onSelect:(r,c,label)=>{
            if(r===row&&c===0){player.ui.currentMenuId="codexBulletTime";return false;}
            return onSelect(r,c,label);
        }};
});
Instance.RegisterCheatCommand("aktimescale",args=>__codexSetBulletTime(args.trim()));
Instance.RegisterCheatCommand("akslowmenu",()=>{
    const player=PlayerMgr.resolveUser();if(!player?.ui)return;
    player.ui.currentMenuId="codexBulletTime";player.ui.openMenu();
});
__codexApplyBulletTime();
Instance.Msg("[BULLET-TIME] double-Tab menu installed (0.10–1.00)");
