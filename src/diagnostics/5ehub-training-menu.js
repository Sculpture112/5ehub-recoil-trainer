// Local training controls share the guide's state and target anchor.
const __codexTrainingMenuProvider=_menuProvider;
const __codexAimPartNames={head:"头部",neck:"脖子",chest:"身体"};
const __codexGuideWhenNames={always:"持续显示",fire:"开火后显示",visible:"看见 Bot 时显示"};
const __codexGuideResolutions={
    "4:3":[[1024,768],[1152,864],[1280,960],[1440,1080],[1600,1200],[1920,1440]],
    "16:10":[[1280,800],[1440,900],[1680,1050],[1920,1200],[2560,1600],[3840,2400]],
    "16:9":[[1280,720],[1600,900],[1920,1080],[2560,1440],[3840,2160]]
};
let __codexGuideAspect="4:3";
let __codexGuideWeaponPage=0;
registerMenuProvider(player=>{
    if(player.ui.currentMenuId==="codexGuideWhen"){
        const selected=value=>(__5ehubGuideWhen===value?"✓ ":"")+__codexGuideWhenNames[value];
        return {
            title:"轨迹显示时机 · "+__codexGuideWhenNames[__5ehubGuideWhen],
            items:[[selected("fire"),selected("always")],[selected("visible")],["返回"]],
            footer:"看见 Bot：出现在视野内且未被墙遮挡；两种绘制版本共用。",
            onSelect:(row,col)=>{
                const value=[["fire","always"],["visible"]][row]?.[col];
                if(value)__5ehubSetGuideWhen(value);
                else if(row===2&&col===0)player.ui.currentMenuId="codexAimSettings";
                return false;
            }
        };
    }
    if(player.ui.currentMenuId==="codexDrawingVersion"){
        const selected=version=>(__5ehubDrawingVersion()===version?"✓ ":"")+(version===1?"第一版":"第二版");
        return {
            title:"绘制切换 · "+(__5ehubDrawingVersion()===1?"第一版":"第二版"),
            items:[[selected(1),selected(2)],["返回"]],
            footer:"第一版：最初全枪械版；第二版：当前版本。选择后立即生效。",
            onSelect:(row,col)=>{
                if(row===0&&(col===0||col===1))__5ehubSetDrawingVersion(col+1);
                else if(row===1&&col===0)player.ui.currentMenuId="codexAimSettings";
                return false;
            }
        };
    }
    if(player.ui.currentMenuId==="codexGuideWeapon"){
        const weapons=__5ehubWeaponCatalog.filter(p=>!p.scoped&&__5ehubWeaponProfiles[p.key]?.recoil.length).map(p=>p.key);
        const pages=Math.max(1,Math.ceil(weapons.length/10));
        __codexGuideWeaponPage=Math.max(0,Math.min(__codexGuideWeaponPage,pages-1));
        const offset=__codexGuideWeaponPage*10,visible=weapons.slice(offset,offset+10),items=[];
        for(let i=0;i<visible.length;i+=2)items.push(visible.slice(i,i+2).map(name=>__5ehubWeaponProfiles[name].label));
        const navRow=items.length;
        if(pages>1)items.push([__codexGuideWeaponPage>0?"上一页":"",__codexGuideWeaponPage<pages-1?"下一页":""]);
        const returnRow=items.length;items.push(["返回"]);
        return {
            title:"选择训练武器 · "+(__codexGuideWeaponPage+1)+"/"+pages,
            items,
            footer:__5ehubProfileName==="weapon_cz75a"?"CZ75 为平均参考轨迹，实际落点仍可能波动。":"AUG/SG 553 随开镜切换；M4A1-S 装消音器；FAMAS 使用全自动。",
            onSelect:(row,col)=>{
                const name=row>=0&&row<Math.ceil(visible.length/2)?visible[row*2+col]:undefined;
                if(name)__5ehubEquipWeapon(name).catch(e=>Instance.Msg("[GUN-GUIDE] equip error="+String(e)));
                else if(pages>1&&row===navRow&&col===0&&__codexGuideWeaponPage>0)__codexGuideWeaponPage--;
                else if(pages>1&&row===navRow&&col===1&&__codexGuideWeaponPage<pages-1)__codexGuideWeaponPage++;
                else if(row===returnRow&&col===0)player.ui.currentMenuId="codexAimSettings";
                return false;
            }
        };
    }
    if(player.ui.currentMenuId==="codexGuideAspect"){
        return {
            title:"画面适配 · 当前 "+__5ehubViewport.width+"×"+__5ehubViewport.height,
            items:[["4:3","16:10"],["16:9","返回"]],
            footer:"选择游戏内宽高比，再选实际分辨率。",
            onSelect:(row,col)=>{
                const aspect=[["4:3","16:10"],["16:9"]][row]?.[col];
                if(aspect){__codexGuideAspect=aspect;player.ui.currentMenuId="codexGuideResolution";}
                else if(row===1&&col===1)player.ui.currentMenuId="codexAimSettings";
                return false;
            }
        };
    }
    if(player.ui.currentMenuId==="codexGuideResolution"){
        const resolutions=__codexGuideResolutions[__codexGuideAspect],items=[];
        for(let i=0;i<resolutions.length;i+=2)items.push(resolutions.slice(i,i+2).map(([w,h])=>(w===__5ehubViewport.width&&h===__5ehubViewport.height?"✓ ":"")+w+"×"+h));
        const returnRow=items.length;
        items.push(["返回宽高比","返回训练设置"]);
        return {
            title:__codexGuideAspect+" · 当前 "+__5ehubViewport.width+"×"+__5ehubViewport.height,
            items,footer:"必须与游戏实际分辨率一致，选后立即生效。",
            onSelect:(row,col)=>{
                if(row>=0&&row<returnRow&&(col===0||col===1)){
                    const size=resolutions[row*2+col];if(size)__5ehubSetViewport(...size);
                }else if(row===returnRow&&col===0)player.ui.currentMenuId="codexGuideAspect";
                else if(row===returnRow&&col===1)player.ui.currentMenuId="codexAimSettings";
                return false;
            }
        };
    }
    if(player.ui.currentMenuId==="codexAimSettings"){
        const selected=part=>(__5ehubRmPart===part?"✓ ":"")+__codexAimPartNames[part];
        return {
            title:"自瞄与目标 · "+(__5ehubAuto?"开启":"关闭")+" · "+__codexAimPartNames[__5ehubRmPart],
            items:[["自瞄："+(__5ehubAuto?"开启":"关闭"),...(__5ehubDisplay==="screen"?["画面适配"]:[])],[selected("head"),selected("neck")],[selected("chest"),"返回主菜单"],["选择武器","轨迹显示："+(__5ehubRmGuideEnabled?"开启":"关闭")],["屏幕晃动："+(__5ehubScreenShake?"开启":"关闭")],["绘制切换："+(__5ehubDrawingVersion()===1?"第一版":"第二版")],["显示时机："+__codexGuideWhenNames[__5ehubGuideWhen]]],
            footer:__5ehubDisplay==="world"?"画面自动适配；目标部位同时用于自瞄与轨迹。":"开火时自动瞄准并压枪；目标部位同时用于轨迹。",
            onSelect:(row,col)=>{
                if(row===0&&col===0)__5ehubAuto=!__5ehubAuto;
                else if(row===0&&col===1&&__5ehubDisplay==="screen")player.ui.currentMenuId="codexGuideAspect";
                else if(row===1&&col===0)__5ehubRmPart="head";
                else if(row===1&&col===1)__5ehubRmPart="neck";
                else if(row===2&&col===0)__5ehubRmPart="chest";
                else if(row===2&&col===1)player.ui.currentMenuId="testMenu";
                else if(row===3&&col===0){__codexGuideWeaponPage=0;player.ui.currentMenuId="codexGuideWeapon";}
                else if(row===3&&col===1){__5ehubRmGuideEnabled=!__5ehubRmGuideEnabled;if(!__5ehubRmGuideEnabled)__5ehubRmHide();}
                else if(row===4&&col===0)__5ehubSetScreenShake(!__5ehubScreenShake);
                else if(row===5&&col===0)player.ui.currentMenuId="codexDrawingVersion";
                else if(row===6&&col===0)player.ui.currentMenuId="codexGuideWhen";
                return false;
            }
        };
    }
    const data=__codexTrainingMenuProvider(player);
    if(player.ui.currentMenuId!=="testMenu")return data;
    const row=data.items.findIndex(items=>items[0]?.startsWith("子弹时间："));
    if(row<0)return data;
    const items=data.items.map((items,index)=>index===row?[...items,"自瞄与目标"]:items);
    return {...data,items,onSelect:(r,c,label)=>{
        if(r===row&&c===1){player.ui.currentMenuId="codexAimSettings";return false;}
        return data.onSelect(r,c,label);
    }};
});
Instance.Msg("[AK-MENU] double-Tab aim, target and 4:3/16:10/16:9 viewport settings installed");
