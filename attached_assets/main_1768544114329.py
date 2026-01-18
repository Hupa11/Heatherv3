import requests
import telebot,time
from telebot import types
from gatet import Tele
import os
token = '8523350257:AAHOwmx5NnfI-8LsjfcDxEGf7bG0f6pEuWc' #Add Token
bot=telebot.TeleBot(token,parse_mode="HTML")
@bot.message_handler(commands=["start"])
def start(message):
	if not str(message.chat.id) == '7102484985':
	#add chat id 
		bot.reply_to(message, "You cannot use the bot to contact developers to purchase a bot subscription @botcodexx")
		return
	bot.reply_to(message,"Send the file now")
@bot.message_handler(content_types=["document"])
def main(message):
	if not str(message.chat.id) == '7102484985': #add chat id 
		bot.reply_to(message, "You cannot use the bot to contact developers to purchase a bot subscription @botcodexx")
		return
	dd = 0
	live = 0
	ch = 0
	ccn = 0
	cvv = 0
	lowfund = 0
	ko = (bot.reply_to(message, "CHECKING....⌛").message_id)
	ee = bot.download_file(bot.get_file(message.document.file_id).file_path)
	with open("combo.txt", "wb") as w:
		w.write(ee)
	try:
		with open("combo.txt", 'r') as file:
			lino = file.readlines()
			total = len(lino)
			for cc in lino:
				current_dir = os.getcwd()
				for filename in os.listdir(current_dir):
					if filename.endswith(".stop"):
						bot.edit_message_text(chat_id=message.chat.id, message_id=ko, text='STOP ✅\nBOT BY ➜ @botcodexx')
						os.remove('stop.stop')
						return
				try: data = requests.get('https://bins.antipublic.cc/bins/'+cc[:6]).json()
				except: pass
				try:
					brand = data['brand']
				except:
					brand = 'Unknown'
				try:
					card_type = data['type']
				except:
					card_type = 'Unknown'
				try:
					country = data['country_name']
					country_flag = data['country_flag']
				except:
					country = 'Unknown'
					country_flag = 'Unknown'
				try:
					bank = data['bank']
				except:
					bank = 'Unknown'
				
				start_time = time.time()
				try:
					last = str(Tele(cc))
				except Exception as e:
					print(e)
					last = 'missing payment form'
				mes = types.InlineKeyboardMarkup(row_width=1)
				cm1 = types.InlineKeyboardButton(f"• {cc} •", callback_data='u8')
				status = types.InlineKeyboardButton(f"• STATUS ➜ {last} •", callback_data='u8')
				cm3 = types.InlineKeyboardButton(f"• CHARGED ➜ [ {ch} ] •", callback_data='x')
				cm4 = types.InlineKeyboardButton(f"• CCN ➜ [ {ccn} ] •", callback_data='x')
				cm5 = types.InlineKeyboardButton(f"• CVV ➜ [ {cvv} ] •", callback_data='x')
				cm6 = types.InlineKeyboardButton(f"• LOW FUNDS ➜ [ {lowfund} ] •", callback_data='x')
				cm7 = types.InlineKeyboardButton(f"• DECLINED ➜ [ {dd} ] •", callback_data='x')
				cm8 = types.InlineKeyboardButton(f"• TOTAL ➜ [ {total} ] •", callback_data='x')
				stop=types.InlineKeyboardButton(f"[ STOP ]", callback_data='stop')
				mes.add(cm1,status, cm3, cm4, cm5, cm6, cm7, cm8, stop)
				end_time = time.time()
				execution_time = end_time - start_time
				bot.edit_message_text(chat_id=message.chat.id, message_id=ko, text='''Wait For Processing   
by ➜ @botcodexx''', reply_markup=mes)
				msg = f"""
✨✨ 𝐂𝐀𝐑𝐃 𝐂𝐇𝐄𝐂𝐊 𝐑𝐄𝐒𝐔𝐋𝐓 ✨✨
━━━━━━━━━━━━━━━━━━
💳 <b>𝐂𝐀𝐑𝐃</b>
<code>{cc}</code>

[ϟ] <b>𝐑𝐄𝐒𝐏𝐎𝐍𝐒𝐄</b>
<code>Payment Successful! $1.00 🔥</code>

━━━━━━━━━━━━━━━━━━
🏦 <b>𝐁𝐈𝐍 𝐈𝐍𝐅𝐎</b>
<code>{cc[:6]} • {card_type} • {brand}</code>

🏛 <b>𝐁𝐀𝐍𝐊</b>
<code>{bank}</code>

🌍 <b>𝐂𝐎𝐔𝐍𝐓𝐑𝐘</b>
<code>{country} {country_flag}</code>

⏱ <b>𝐓𝐈𝐌𝐄</b>
<code>{execution_time:.1f} sec</code>

━━━━━━━━━━━━━━━━━━
🤖 <b>𝐁𝐎𝐓</b>
<b>@botcodexx</b>
"""
				
				print(last)
				if 'Donation Successful!' in last:
					ch += 1
					bot.reply_to(message, msg)
					
				elif 'Your card does not support this type of purchase' in last:
				    cvv += 1
				    				    
				elif 'security code is incorrect' in last or 'security code is invalid' in last:
					ccn += 1
					
				elif 'insufficient funds' in last:
					msg = f"""
✨✨ 𝐂𝐀𝐑𝐃 𝐂𝐇𝐄𝐂𝐊 𝐑𝐄𝐒𝐔𝐋𝐓 ✨✨
━━━━━━━━━━━━━━━━━━
💳 <b>𝐂𝐀𝐑𝐃</b>
<code>{cc}</code>

[ϟ] <b>𝐑𝐄𝐒𝐏𝐎𝐍𝐒𝐄</b>
<code>Insufficient🔥</code>

━━━━━━━━━━━━━━━━━━
🏦 <b>𝐁𝐈𝐍 𝐈𝐍𝐅𝐎</b>
<code>{cc[:6]} • {card_type} • {brand}</code>

🏛 <b>𝐁𝐀𝐍𝐊</b>
<code>{bank}</code>

🌍 <b>𝐂𝐎𝐔𝐍𝐓𝐑𝐘</b>
<code>{country} {country_flag}</code>

⏱ <b>𝐓𝐈𝐌𝐄</b>
<code>{execution_time:.1f} sec</code>

━━━━━━━━━━━━━━━━━━
🤖 <b>𝐁𝐎𝐓</b>
<b>@botcodexx</b>
"""
					lowfund += 1
					bot.reply_to(message, msg)
					
				elif 'The payment needs additional action before completion!' in last:
					msg = f'''			
𝐂𝐀𝐑𝐃: <code>{cc}</code>
𝐑𝐞𝐬𝐩𝐨𝐧𝐬𝐞: <code>3ds ✅</code>

𝐁𝐢𝐧 𝐈𝐧𝐟𝐨: <code>{cc[:6]}-{card_type} - {brand}</code>
𝐁𝐚𝐧𝐤: <code>{bank}</code>
𝐂𝐨𝐮𝐧𝐭𝐫𝐲: <code>{country} - {country_flag}</code>

𝐓𝐢𝐦𝐞: <code>{execution_time:.1f} second</code> 
𝐁𝐨𝐭 𝐀𝐛𝐨𝐮𝐭: @botcodexx'''
					cvv += 1
					bot.reply_to(message, msg)

				else:
					dd += 1
					bot.reply_to(message, msg)
					time.sleep(5)
	except Exception as e:
		print(e)
	bot.edit_message_text(chat_id=message.chat.id, message_id=ko, text='CHECKED ✅\nBOT BY ➜ @botcodexx')
@bot.callback_query_handler(func=lambda call: call.data == 'stop')
def menu_callback(call):
	with open("stop.stop", "w") as file:
		pass
if __name__ == "__main__":
    bot.infinity_polling(timeout=10, long_polling_timeout=5)


#BotCodexx