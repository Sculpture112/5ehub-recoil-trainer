const fs = require('fs'), path = require('path'), vm = require('vm'), assert = require('assert/strict');
const root=path.resolve(__dirname,'..');
const source=fs.readFileSync(path.join(root,'src/extension.js'),'utf8');
const begin=source.indexOf('let __5ehubBotInvincible='),end=source.indexOf('function __5ehubPublishShakeState',begin);
const bot={GetOriginalPlayerController:()=>({IsBot:()=>true})};
let mode='peek',menu;
const ctx=vm.createContext({Instance:{Msg(){}},ModeMgr:{getCurrentModeId:()=>mode},peekMode:{victim:bot},
  registerMenuProvider:p=>menu=p,_menuProvider:()=>({}),__5ehubAuto:false,__5ehubRmPart:'head',
  __5ehubDisplay:'world',__5ehubRmGuideEnabled:true,__5ehubScreenShake:false,__5ehubGuideWhen:'always',__5ehubDrawingVersion:()=>2});
vm.runInContext(source.slice(begin,end),ctx);
vm.runInContext(fs.readFileSync(path.join(root,'src/diagnostics/5ehub-training-menu.js'),'utf8'),ctx);
const blocked=p=>ctx.__5ehubBlockBotDamage({player:p});
assert.equal(blocked(bot),false);
const player={ui:{currentMenuId:'codexAimSettings'}};
assert.equal(menu(player).items[4][1],'Bot 无敌：关闭');
menu(player).onSelect(4,1);
assert.equal(menu(player).items[4][1],'Bot 无敌：开启');
assert.equal(blocked(bot),true);
assert.equal(blocked({GetOriginalPlayerController:()=>({IsBot:()=>false})}),false);
assert.equal(blocked({GetOriginalPlayerController:()=>({IsBot:()=>true})}),false);
mode='recoil';assert.equal(blocked(bot),false);mode='peek';
menu(player).onSelect(4,1);assert.equal(blocked(bot),false);
console.log('PASS: menu toggles only current peek Bot invincibility; other players and modes are unaffected.');
