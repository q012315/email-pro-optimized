#!/usr/bin/env python3
"""
Email Pro Optimized - 高性能邮件工具
支持: 检查、搜索、发送、删除邮件
"""

import imaplib
import smtplib
import json
import ssl
import sys
import argparse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.parser import BytesParser
from email import encoders
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

CONFIG_FILE = Path.home() / '.openclaw' / 'credentials' / 'email-accounts.json'

class EmailProOptimized:
    def __init__(self, account='qq_3421'):
        self.account_name = account
        self.config = self._load_config(account)
        self.imap = None
        self.smtp = None
        
    def _load_config(self, account):
        if not CONFIG_FILE.exists():
            raise FileNotFoundError(f"配置文件不存在: {CONFIG_FILE}")
        
        with open(CONFIG_FILE, 'r') as f:
            accounts = json.load(f)
        
        if account not in accounts:
            raise ValueError(f"账户不存在: {account}")
        
        return accounts[account]
    
    def _connect_imap(self):
        """连接 IMAP（复用连接）"""
        if self.imap is None:
            context = ssl.create_default_context()
            self.imap = imaplib.IMAP4_SSL(
                self.config['imap_server'],
                self.config['imap_port'],
                ssl_context=context
            )
            self.imap.login(self.config['email'], self.config['auth_code'])
        return self.imap
    
    def _disconnect_imap(self):
        """断开 IMAP 连接"""
        if self.imap:
            try:
                self.imap.close()
                self.imap.logout()
            except:
                pass
            self.imap = None
    
    def check_emails(self, limit=10, unread_only=False, mailbox='INBOX'):
        """快速检查邮件 - 优化版"""
        try:
            imap = self._connect_imap()
            imap.select(mailbox)
            
            criteria = 'UNSEEN' if unread_only else 'ALL'
            status, messages = imap.search(None, criteria)
            
            if not messages[0]:
                return []
            
            msg_ids = messages[0].split()[-limit:]
            
            # 关键优化: 批量 fetch (4.5x 快)
            if msg_ids:
                status, msg_data_list = imap.fetch(b','.join(msg_ids), '(RFC822)')
            else:
                return []
            
            results = []
            i = 0
            while i < len(msg_data_list):
                if isinstance(msg_data_list[i], tuple):
                    try:
                        msg = BytesParser().parsebytes(msg_data_list[i][1])
                        results.append({
                            'from': msg.get('From', 'Unknown'),
                            'subject': msg.get('Subject', '(no subject)'),
                            'date': msg.get('Date', ''),
                            'uid': msg_data_list[i][0].decode() if isinstance(msg_data_list[i][0], bytes) else str(msg_data_list[i][0]),
                            'snippet': self._get_snippet(msg),
                        })
                    except:
                        pass
                i += 1
            
            return results
        
        except Exception as e:
            print(f"❌ 检查邮件失败: {e}", file=sys.stderr)
            return []
    
    def fetch_email(self, uid, mailbox='INBOX'):
        """获取完整邮件"""
        try:
            imap = self._connect_imap()
            imap.select(mailbox)
            
            status, msg_data = imap.fetch(uid, '(RFC822)')
            msg = BytesParser().parsebytes(msg_data[0][1])
            
            return {
                'from': msg.get('From'),
                'to': msg.get('To'),
                'subject': msg.get('Subject'),
                'date': msg.get('Date'),
                'body': self._get_body(msg),
                'attachments': self._get_attachments(msg),
            }
        
        except Exception as e:
            print(f"❌ 获取邮件失败: {e}", file=sys.stderr)
            return None
    
    def search_emails(self, query='', limit=20, mailbox='INBOX'):
        """搜索邮件 - 优化版"""
        try:
            imap = self._connect_imap()
            imap.select(mailbox)
            
            criteria = ['ALL']
            if query:
                criteria = ['OR', 'FROM', query, 'SUBJECT', query]
            
            status, messages = imap.search(None, *criteria)
            
            if not messages[0]:
                return []
            
            msg_ids = messages[0].split()[-limit:]
            
            # 批量 fetch
            if msg_ids:
                status, msg_data_list = imap.fetch(b','.join(msg_ids), '(RFC822)')
            else:
                return []
            
            results = []
            i = 0
            while i < len(msg_data_list):
                if isinstance(msg_data_list[i], tuple):
                    try:
                        msg = BytesParser().parsebytes(msg_data_list[i][1])
                        results.append({
                            'from': msg.get('From'),
                            'subject': msg.get('Subject'),
                            'date': msg.get('Date'),
                            'uid': msg_data_list[i][0].decode() if isinstance(msg_data_list[i][0], bytes) else str(msg_data_list[i][0]),
                            'snippet': self._get_snippet(msg),
                        })
                    except:
                        pass
                i += 1
            
            return results
        
        except Exception as e:
            print(f"❌ 搜索邮件失败: {e}", file=sys.stderr)
            return []
    
    def delete_emails(self, senders=None, mailbox='INBOX'):
        """删除指定发件人的邮件"""
        if senders is None:
            senders = []
        
        try:
            imap = self._connect_imap()
            imap.select(mailbox)
            
            total_deleted = 0
            
            for sender in senders:
                print(f"🔍 搜索 {sender}...")
                
                try:
                    status, messages = imap.search(None, 'FROM', sender)
                    msg_ids = messages[0].split()
                    
                    if msg_ids:
                        print(f"  找到 {len(msg_ids)} 封")
                        
                        # 分批删除
                        batch_size = 50
                        for i in range(0, len(msg_ids), batch_size):
                            batch = msg_ids[i:i+batch_size]
                            imap.store(b','.join(batch), '+FLAGS', '\\Deleted')
                            print(f"    已标记删除 {min(i+batch_size, len(msg_ids))}/{len(msg_ids)}")
                            time.sleep(0.2)
                        
                        total_deleted += len(msg_ids)
                    else:
                        print(f"  找到 0 封")
                
                except Exception as e:
                    print(f"  ❌ 错误: {e}")
            
            # 永久删除
            print(f"\n⏳ 正在永久删除...")
            imap.expunge()
            
            print(f"\n✅ 完成！共删除 {total_deleted} 封邮件")
            return total_deleted
        
        except Exception as e:
            print(f"❌ 删除邮件失败: {e}", file=sys.stderr)
            return 0
    
    def send_email(self, to, subject, body, html=False, attachments=None):
        """发送邮件"""
        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = self.config['email']
            msg['To'] = to
            msg['Subject'] = subject
            
            if html:
                msg.attach(MIMEText(body, 'html'))
            else:
                msg.attach(MIMEText(body, 'plain'))
            
            if attachments:
                for file_path in attachments:
                    self._attach_file(msg, file_path)
            
            context = ssl.create_default_context()
            smtp = smtplib.SMTP(
                self.config['smtp_server'],
                self.config['smtp_port'],
                context=context
            )
            smtp.starttls()
            smtp.login(self.config['email'], self.config['auth_code'])
            smtp.send_message(msg)
            smtp.quit()
            
            print(f"✅ 邮件已发送给 {to}")
            return True
        
        except Exception as e:
            print(f"❌ 发送邮件失败: {e}", file=sys.stderr)
            return False
    
    def batch_fetch(self, uids, mailbox='INBOX', max_workers=5):
        """并发获取多封邮件"""
        try:
            results = []
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(self.fetch_email, uid, mailbox): uid 
                    for uid in uids
                }
              
                for future in as_completed(futures):
                    result = future.result()
                    if result:
                        results.append(result)
            
            return results
        
        except Exception as e:
            print(f"❌ 批量获取失败: {e}", file=sys.stderr)
            return []
    
    def list_accounts(self):
        """列出所有账户"""
        with open(CONFIG_FILE, 'r') as f:
            accounts = json.load(f)
        
        print("\n📧 已配置的邮箱账户:\n")
        for name, config in accounts.items():
            email = config.get('email')
            status = config.get('status', '⚠️ 未知')
            note = config.get('note', '')
            print(f"  {name:15} | {email:25} | {status:10} | {note}")
        print()
    
    def _get_body(self, msg):
        """提取邮件正文"""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == 'text/plain':
                    payload = part.get_payload(decode=True)
                    if payload:
                        return payload.decode('utf-8', errors='ignore')
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                return payload.decode('utf-8', errors='ignore')
        return ''
    
    def _get_snippet(self, msg):
        """获取邮件摘要"""
        body = self._get_body(msg)
        return body[:200] if body else '(no content)'
    
    def _get_attachments(self, msg):
        """获取附件列表"""
        attachments = []
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_disposition() == 'attachment':
                    filename = part.get_filename()
                    if filename:
                        attachments.append({
                            'filename': filename,
                            'size': len(part.get_payload(decode=True)),
                        })
        return attachments
    
    def _attach_file(self, msg, file_path):
        """添加附件"""
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        with open(file_path, 'rb') as attachment:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(attachment.read())
        
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename={file_path.name}')
        msg.attach(part)
    
    def __del__(self):
        """清理资源"""
        self._disconnect_imap()


def main():
    parser = argparse.ArgumentParser(description='📧 Email Pro Optimized - 高性能邮件工具')
    parser.add_argument('--account', default='qq_3421', help='账户名称')
    
    subparsers = parser.add_subparsers(dest='command', help='命令')
    
    check_parser = subparsers.add_parser('check', help='检查邮件')
    check_parser.add_argument('--limit', type=int, default=10, help='限制数量')
    check_parser.add_argument('--unread', action='store_true', help='仅未读')
    check_parser.add_argument('--mailbox', default='INBOX', help='邮箱')
    
    fetch_parser = subparsers.add_parser('fetch', help='获取邮件')
    fetch_parser.add_argument('uid', help='邮件 UID')
    fetch_parser.add_argument('--mailbox', default='INBOX', help='邮箱')
    
    search_parser = subparsers.add_parser('search', help='搜索邮件')
    search_parser.add_argument('query', help='搜索关键词')
    search_parser.add_argument('--limit', type=int, default=20, help='限制数量')
    search_parser.add_argument('--mailbox', default='INBOX', help='邮箱')
    
    delete_parser = subparsers.add_parser('delete', help='删除邮件')
    delete_parser.add_argument('senders', nargs='+', help='发件人名称')
    delete_parser.add_argument('--mailbox', default='INBOX', help='邮箱')
    
    send_parser = subparsers.add_parser('send', help='发送邮件')
    send_parser.add_argument('--to', required=True, help='收件人')
    send_parser.add_argument('--subject', required=True, help='主题')
    send_parser.add_argument('--body', required=True, help='正文')
    send_parser.add_argument('--html', action='store_true', help='HTML 格式')
    send_parser.add_argument('--attach', nargs='+', help='附件')
    
    subparsers.add_parser('list-accounts', help='列出账户')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    email = EmailProOptimized(args.account)
    
    if args.command == 'check':
        results = email.check_emails(args.limit, args.unread, args.mailbox)
        print(json.dumps(results, indent=2, ensure_ascii=False))
    
    elif args.command == 'fetch':
        result = email.fetch_email(args.uid, args.mailbox)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    elif args.command == 'search':
        results = email.search_emails(args.query, args.limit, args.mailbox)
        print(json.dumps(results, indent=2, ensure_ascii=False))
    
    elif args.command == 'delete':
        email.delete_emails(args.senders, args.mailbox)
    
    elif args.command == 'send':
        email.send_email(args.to, args.subject, args.body, args.html, args.attach)
    
    elif args.command == 'list-accounts':
        email.list_accounts()

if __name__ == '__main__':
    main()
