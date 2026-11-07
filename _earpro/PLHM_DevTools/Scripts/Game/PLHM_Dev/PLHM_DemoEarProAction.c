// PLHM_DevTools (test only, never shipped): demo actions on a box so a tester can trigger the ear-pro on himself in MP.
class PLHM_DemoEarProAction : ScriptedUserAction
{
	[Attribute("8", desc: "8 toggle stow, 9 toggle vent (PLHM_EEarProRequest) or 1-4 explicit action")]
	protected int m_iRequest;

	[Attribute("3", desc: "cups: 1 left, 2 right, 3 both")]
	protected int m_iMask;

	override bool CanBeShownScript(IEntity user)
	{
		return PLHM_EarProService.FindEarPro(user) != null;
	}

	override bool CanBePerformedScript(IEntity user)
	{
		PLHM_EarProComponent ep = PLHM_EarProService.FindEarPro(user);
		return ep && !ep.IsBusy();
	}

	override void PerformAction(IEntity pOwnerEntity, IEntity pUserEntity)
	{
		if (!Replication.IsServer())
			return;
		int pid = GetGame().GetPlayerManager().GetPlayerIdFromControlledEntity(pUserEntity);
		SCR_PlayerController pc = SCR_PlayerController.Cast(GetGame().GetPlayerManager().GetPlayerController(pid));
		if (pc)
			pc.PLHM_ServerHandleRequest(m_iRequest, m_iMask);
	}
}
