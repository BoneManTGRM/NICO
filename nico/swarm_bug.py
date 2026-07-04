import asyncio
from crewai import Agent, Task, Crew

class BugSwarm:
    def __init__(self):
        self.agents = [
            Agent(role='CodeBug', goal='find syntax/logic bugs', backstory='RYE specialist'),
            Agent(role='DepBug', goal='vuln deps'),
            Agent(role='UIBug', goal='parity/UI issues'),
            Agent(role='PerfBug', goal='perf leaks'),
            Agent(role='SecBug', goal='security'),
        ]
    async def swarm(self, repo):
        # parallel RYE-scored bug hunt
        tasks = [Task(description=f'Scan {repo} for bugs', agent=a) for a in self.agents]
        crew = Crew(agents=self.agents, tasks=tasks)
        result = await crew.kickoff()
        return {'bugs': result, 'rye_score': 'high-yield fixes prioritized'}

# Integrated in nico/auditor.py
