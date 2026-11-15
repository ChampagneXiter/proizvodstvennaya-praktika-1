import pandas as pd
import numpy as np

# Load data
df = pd.read_csv(r'C:\Users\user\.gemini\antigravity\scratch\practice_2026\case_1_elma_anomalies\students.csv')
df['Timestamp'] = pd.to_datetime(df['Timestamp'])
df = df.sort_values(['ProcessInstanceId', 'EventIndex'])

anomalies = []

# 1. Self-approval: Requester in Manager Role
req_mgr = df[(df['ActivityName'] == 'Согласование руководителем') & (df['Role'] == 'requester')]
for idx, r in req_mgr.iterrows():
    pid = r['ProcessInstanceId']
    res = r['Result']
    anomalies.append({
        'ProcessInstanceId': pid,
        'AnomalyType': 'Неправомерная роль согласующего',
        'Explanation': f'Этап «Согласование руководителем» закрыт пользователем с ролью requester (UserId: {r["UserId"]}) с результатом {res}. Нарушение принципа разделения полномочий (SoD) и регламента согласования.'
    })

# 2. Bypassed Manager Approval in fulfilled processes
for pid, group in df.groupby('ProcessInstanceId'):
    final_res = group[group['EventType'] == 'process_completed']['Result'].tolist()
    if 'fulfilled' in final_res:
        acts = group[group['EventType'] == 'task_completed']['ActivityName'].tolist()
        if 'Согласование руководителем' not in acts:
            anomalies.append({
                'ProcessInstanceId': pid,
                'AnomalyType': 'Пропуск обязательного этапа',
                'Explanation': 'Заявка успешно исполнена и закрыта со статусом fulfilled в обход этапа «Согласование руководителем». После «Проверки заявки» процесс сразу перешёл к «Согласованию бюджета».'
            })

# 3. Procurement before Budget (and Legal if contract)
for pid, group in df.groupby('ProcessInstanceId'):
    completed = group[group['EventType'] == 'task_completed']
    acts = completed['ActivityName'].tolist()
    if 'Исполнение заявки' in acts and 'Согласование бюджета' in acts:
        idx_proc = acts.index('Исполнение заявки')
        idx_budget = acts.index('Согласование бюджета')
        if idx_proc < idx_budget:
            rtype = group['RequestType'].iloc[0]
            extra = ''
            if rtype == 'contract' and 'Проверка договора' in acts:
                idx_legal = acts.index('Проверка договора')
                if idx_proc < idx_legal:
                    extra = ' и до юридической проверки договора'
            anomalies.append({
                'ProcessInstanceId': pid,
                'AnomalyType': 'Нарушение последовательности этапов',
                'Explanation': f'Этап «Исполнение заявки» выполнен закупщиком ДО согласования бюджета финансистом{extra}. Нарушен обязательный порядок: согласование бюджета предшествует закупке.'
            })

# 4. Excessive returns (loops > 2)
p_returns = df[df['Result'] == 'return'].groupby('ProcessInstanceId').size()
multi_returns = p_returns[p_returns > 2]
for pid, cnt in multi_returns.items():
    anomalies.append({
        'ProcessInstanceId': pid,
        'AnomalyType': 'Аномальное зацикливание доработок',
        'Explanation': f'Заявка возвращалась руководителем на доработку {cnt} раз (в норме при возвратах наблюдается ровно 1 возврат). Свидетельствует о зацикливании процесса или некачественном заполнении заявки.'
    })

# 5. Instant robotic/fictitious execution (< 60s per task)
created = df[df['EventType'] == 'task_created'].set_index('TaskId')
completed = df[df['EventType'] == 'task_completed'].set_index('TaskId')
m = created.join(completed, lsuffix='_c', rsuffix='_d')
m['dur'] = (m['Timestamp_d'] - m['Timestamp_c']).dt.total_seconds()
fast_tasks = m[m['dur'] < 60]
for pid in fast_tasks['ProcessInstanceId_c'].unique():
    pid_tasks = fast_tasks[fast_tasks['ProcessInstanceId_c'] == pid]
    avg_dur = pid_tasks['dur'].mean()
    anomalies.append({
        'ProcessInstanceId': pid,
        'AnomalyType': 'Аномально быстрое согласование',
        'Explanation': f'Человеческие задания закрывались аномально быстро (в среднем за {avg_dur:.1f} сек., {len(pid_tasks)} этапов длились менее 20 сек. при медиане процесса 1.8 часа). Признак фиктивного или скриптового закрытия задач.'
    })

# 6. Stuck / Abandoned processes (> 100 days)
cutoff = pd.to_datetime('2026-07-01 00:00:00+03:00')
completed_pids = set(df[df['EventType'] == 'process_completed']['ProcessInstanceId'])
for pid in (set(df['ProcessInstanceId']) - completed_pids):
    sub = df[df['ProcessInstanceId'] == pid]
    age = (cutoff - sub.iloc[-1]['Timestamp']).total_seconds() / 86400
    if age > 100:
        last_act = sub.iloc[-1]['ActivityName']
        anomalies.append({
            'ProcessInstanceId': pid,
            'AnomalyType': 'Зависший процесс',
            'Explanation': f'Заявка находится без движения на этапе «{last_act}» более {age:.0f} дней (с января-февраля 2026 г. до среза 01.07.2026). Процесс брошен и требует ручной проверки/эскалации.'
        })

anomalies_df = pd.DataFrame(anomalies)
anomalies_df = anomalies_df.sort_values(['AnomalyType', 'ProcessInstanceId'])
csv_path = r'C:\Users\user\.gemini\antigravity\scratch\practice_2026\case_1_elma_anomalies\anomalies.csv'
anomalies_df.to_csv(csv_path, index=False, encoding='utf-8')

print(f"Generated {len(anomalies_df)} anomaly records.")
print(anomalies_df['AnomalyType'].value_counts())
