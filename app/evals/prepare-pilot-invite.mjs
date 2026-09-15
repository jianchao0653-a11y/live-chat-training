// Run once for initial handoff. Reuse the same account when reissuing an invite.
import {openCloudAuth} from '../cloud-auth.mjs';
import {existsSync,readFileSync,writeFileSync,mkdirSync} from 'node:fs';
const receipt='runtime/pc-server/pilot-account.json';
const auth=openCloudAuth('runtime/pc-server/data/identity.sqlite');
try{
  const previous=existsSync(receipt)?JSON.parse(readFileSync(receipt,'utf8')):null;
  const invite=auth.invite(previous?.account_id);
  writeFileSync(receipt,JSON.stringify({account_id:invite.account_id}),{mode:0o600});
  mkdirSync('output/native',{recursive:true});
  const guide=`观微 0.16.0 小米安装测试\n\n1. 把 conversation-lens-0.16.0-cloud-release.apk 发送到手机并安装。\n2. 打开观微，进入人物资料/登录，阅读数据处理说明并输入下方邀请码。\n3. 在系统设置启用并选择观微输入法。添加一个虚构人物，提交虚构聊天片段测试建议。由本人编辑、确认插入并发送。\n\n一次性邀请码：${invite.invite}\n有效至：${new Date(invite.expires_at).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'})}（北京时间，单次使用）\n\n电脑需要保持开机联网。项目每天最多20次分析、1元/日、10元/月，达到任一上限即停止（UTC切日，即北京时间08:00）。\n本包尚未完成人工质量和手机完整验收；云端流量正文捕获设置待核对，请先使用虚构片段。\n若旧调试包导致签名冲突，先记录提示并联系开发助手，不要直接卸载可能有未保存资料的旧包。\n邀请码是登录凭据，请勿公开转发。此文件不包含模型Key或ngrok密钥。\n`;
  writeFileSync('output/native/小米安装与登录.txt',guide,{mode:0o600});
  console.log(JSON.stringify({invitePrepared:true,instructions:'output/native/小米安装与登录.txt',expiresAt:invite.expires_at}));
}finally{auth.close();}
