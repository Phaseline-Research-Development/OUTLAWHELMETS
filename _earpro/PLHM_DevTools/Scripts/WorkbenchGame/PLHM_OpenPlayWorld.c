// PLHM_DevTools (test only): -plugin=PLHM_OpenPlayWorld opens the ear-pro play world in the World Editor at startup.
[WorkbenchPluginAttribute(name: "PLHM Open Play World", wbModules: {"WorldEditor"})]
class PLHM_OpenPlayWorld : WorkbenchPlugin
{
	override void RunCommandline()
	{
		Workbench.OpenModule(WorldEditor);
		WorldEditor we = Workbench.GetModule(WorldEditor);
		Print("PLHM_OPEN_WORLD " + we.SetOpenedResource("worlds/PLHM_EarProPlay.ent").ToString());
	}
}
